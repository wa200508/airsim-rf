"""Radio-control interoperation, disabled TX, and physical echo power effects."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from urllib.error import HTTPError
import numpy as np
import pytest
from radar_skill.transceiver import TransceiverClient, configuration_id
from airsim_rf.fmcw import IWR1843Profile
from airsim_rf.radar_control import RadarTransceiverControl,serve_transceiver

ROOT=Path(__file__).resolve().parents[1]


def settings():
    mode=json.loads((ROOT/'scenarios/mmwave-radar/radar-mode.json').read_text())
    config={'sample_rate_hz':10e6,'carrier_hz':77e9,'sites':[{'channels':['radar_rx0']}],
            'acquisition':{**{k:mode['waveform'][k] for k in ('pri_s','bandwidth_hz','chirp_duration_s')},
                           **{k:mode['receiver'][k] for k in ('num_samples','adc_start_s')}}}
    return mode,config


def test_control_is_disabled_until_skill_configures_and_commands_radio():
    mode,config=settings();control=RadarTransceiverControl(IWR1843Profile(),config)
    server=serve_transceiver(control,('127.0.0.1',0));client=TransceiverClient(f'http://127.0.0.1:{server.server_port}')
    try:
        with pytest.raises(RuntimeError):control.begin_window(0)
        with pytest.raises(HTTPError):client.set_state(transmit=True,receive=True)
        result=client.start(mode,ready_timeout=1)
        assert result['configuration_id']==configuration_id(mode)
        profile,transmit=control.begin_window(4_000_000)
        assert transmit and profile.mmic_power_dbm==mode['waveform']['power_dbm']
        assert control.snapshot()['applied_timestamp_ns']==4_000_000
        changed=deepcopy(mode);changed['waveform']['power_dbm']=6
        with pytest.raises(ValueError):control.configure(changed)
        client.set_state(transmit=False,receive=True)
        assert not control.begin_window(8_000_000)[1]
        client.stop()
        with pytest.raises(RuntimeError):control.begin_window(12_000_000)
    finally:server.shutdown();server.server_close()


def test_adapter_rejects_out_of_range_or_truth_bearing_commands():
    mode,config=settings();control=RadarTransceiverControl(IWR1843Profile(),config)
    bad=deepcopy(mode);bad['waveform']['power_dbm']=20
    with pytest.raises(ValueError):control.configure(bad)
    bad=deepcopy(mode);bad['receiver']['target_range_m']=100
    with pytest.raises(ValueError):control.configure(bad)
    assert not control.snapshot()['transmit']


def test_actual_echo_depends_on_commanded_tx_power_and_disappears_with_tx_off():
    pytest.importorskip('sionna.rt')
    import sionna.rt as rt
    from airsim_rf.dashboard_radar import RadarWindowReceiver
    from airsim_rf.radar import PointTarget
    from airsim_rf.scenario_definition import load
    mode,config=settings()
    powers=[]
    for enabled,power in ((False,12.),(True,6.),(True,12.)):
        radio=load('mmwave-radar')['radios'];radio['radar']['profile']['noise_enabled']=False
        radio['radar']['max_depth_per_leg']=0
        receiver=RadarWindowReceiver(rt.load_scene(),radio,config)
        receiver.position=np.zeros(3);receiver.velocity=np.zeros(3);receiver.orientation=np.zeros(3)
        receiver.targets=[PointTarget('target',(50.,0.,0.),100.)]
        mode['waveform']['power_dbm']=power;receiver.control.configure(mode)
        receiver.control.set_state({'transmit':enabled,'receive':True})
        capture=receiver.capture(0,num_samples=400)['radar_rx0']
        powers.append(float(np.mean(abs(capture.input_iq_volts)**2)))
    assert powers[0]==0
    assert powers[1]>0
    assert powers[2]/powers[1]==pytest.approx(10**(.6),rel=1e-5)
