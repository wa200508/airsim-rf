"""Use real GNU Radio to compile/edit generated GRC files and play exact samples.

Run with the system Python used by GNU Radio; absent GNU Radio skips native tests.
"""
import importlib.util
import json
import shutil
import subprocess
import sys
import numpy as np
import pytest
from airsim_rf.sample_recording import SampleRecordingWriter
from airsim_rf.sample_stream import SampleBlock


@pytest.fixture
def archive(tmp_path):
    root=tmp_path/'original'/'iq'
    rate=1e6;count=1024;channels=['site0_e0','site0_e1','site1_e0','site1_e1']
    config={'sample_rate_hz':rate,'carrier_hz':433e6,'sites':[
        {'id':'site0','channels':channels[:2]},{'id':'site1','channels':channels[2:]}]}
    writer=SampleRecordingWriter(root,config);expected={name:[] for name in channels}
    for window in range(3):
        time=window*count+np.arange(count)
        groups=[]
        for index,name in enumerate(channels):
            # Independent amplitudes/phase with evolving frequency, preserved exactly.
            values=((.001+index*.002)*np.exp(1j*(index+.1*time+1e-6*time*time))).astype(np.complex64)
            expected[name].append(values)
            groups.append(SampleBlock(name,values,window*count,5_000_000+window*count*1000,rate,433e6,0.))
        writer.write_window(groups)
    writer.close()
    # The container-only source path must never leak into the generated graph.
    relocated=tmp_path/'relocated archive with spaces'
    shutil.move(root,relocated)
    return relocated,{name:np.concatenate(values) for name,values in expected.items()}


def test_archives_include_portable_stock_complex_file_sources(archive):
    root,expected=archive
    for filename in ('replay.grc','view.grc'):
        graph=json.loads((root/filename).read_text())
        sources=[b for b in graph['blocks'] if b['id']=='blocks_file_source']
        assert len(sources)==len(expected)
        assert all(b['parameters']['type']=='complex' and b['parameters']['repeat']=='False' for b in sources)
        assert all(b['parameters']['offset']=='start_sample' for b in sources)
        assert all(b['parameters']['length']=='sample_count - start_sample' for b in sources)
        assert '/tmp/' not in (root/filename).read_text() and '/run/' not in (root/filename).read_text()
        assert len([b for b in graph['blocks'] if b['id']=='blocks_throttle'])==1
    assert set(p.name for p in root.glob('*.sigmf-data'))=={name+'.sigmf-data' for name in expected}


def test_existing_archive_can_add_graphs_without_changing_samples(archive):
    root,expected=archive
    for filename in ('replay.grc','view.grc'):(root/filename).unlink()
    result=subprocess.run([sys.executable,'-m','airsim_rf.sample_recording','gnuradio',str(root)],
        capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
    assert len(json.loads(result.stdout)['files'])==2
    for name,values in expected.items():
        assert (root/(name+'.sigmf-data')).read_bytes()==values.tobytes()


def compile_graph(root,filename,tmp_path):
    pytest.importorskip('gnuradio.gr')
    if shutil.which('grcc') is None:pytest.skip('GNU Radio Companion compiler not installed')
    output=tmp_path/'generated';output.mkdir(exist_ok=True)
    result=subprocess.run(['grcc','-o',str(output),str(root/filename)],text=True,capture_output=True,timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    graph_id='iq_view' if filename=='view.grc' else 'iq_replay'
    module_path=output/(graph_id+'.py')
    spec=importlib.util.spec_from_file_location(graph_id,module_path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module,getattr(module,graph_id),module_path


@pytest.mark.parametrize('start_sample',[0,1137])
def test_native_file_sources_reproduce_all_channels_exactly_after_relocation(archive,tmp_path,start_sample):
    root,expected=archive
    _,graph,_=compile_graph(root,'replay.grc',tmp_path)
    from gnuradio import blocks
    flow=graph(recording_dir=str(root),start_sample=start_sample,playback_speed=100.)
    sinks=[]
    for index,name in enumerate(expected):
        sink=blocks.vector_sink_c();sinks.append(sink)
        flow.connect((flow.coherent_split,index),sink)
    flow.run()
    for name,sink in zip(expected,sinks):
        actual=np.asarray(sink.data(),dtype=np.complex64)
        assert actual.tobytes()==expected[name][start_sample:].tobytes()


def test_native_generated_headless_command_runs_to_eof(archive,tmp_path):
    root,_=archive
    _,_,script=compile_graph(root,'replay.grc',tmp_path)
    result=subprocess.run([sys.executable,str(script),'--recording-dir',str(root),
        '--playback-speed','100'],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr


def test_native_viewer_opens_and_channel_selection_works(archive,tmp_path,monkeypatch):
    pytest.importorskip('gnuradio.qtgui')
    from PyQt5 import Qt
    from gnuradio import blocks
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen')
    application=Qt.QApplication.instance() or Qt.QApplication([])
    root,expected=archive
    description=json.loads((root/'view.grc').read_text())
    next(b for b in description['blocks'] if b['name']=='view_channel')['parameters']['value']='2'
    (root/'view.grc').write_text(json.dumps(description))
    _,graph,_=compile_graph(root,'view.grc',tmp_path)
    flow=graph(recording_dir=str(root),playback_speed=100.)
    assert flow._view_channel_combo_box.count()==len(expected)
    assert flow.view_channel==2
    sink=blocks.vector_sink_c();flow.connect(flow.channel_selector,sink)
    flow.show();application.processEvents()
    try:
        flow.run();application.processEvents()
        actual=np.asarray(sink.data(),dtype=np.complex64)
        assert actual.tobytes()==expected['site1_e0'].tobytes()
        # GNU Radio 3.10.5's selector learns ninputs when the scheduler starts.
        # Exercise the live chooser only after that initialization.
        flow._view_channel_combo_box.setCurrentIndex(0)
        assert flow.view_channel==0
    finally:
        flow.stop();flow.wait();flow.close();application.processEvents()
