"""Fetch the checksum-pinned upstream Linux Blocks environment for headless checks."""
import argparse
import hashlib
from pathlib import Path
import stat
import urllib.request
import zipfile

URL='https://github.com/iamaisim/ProjectAirSim/releases/download/v1.0.1/Blocks-Linux-1.0.1.zip'
SHA256='4a0c7b6de27ed32bdf4de1c31c222c19b796500108b654382b5d76b4ba000040'


def prepare(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    archive=output/'Blocks-Linux-1.0.1.zip'
    if not archive.exists():
        temporary=output/'download.partial'
        urllib.request.urlretrieve(URL,temporary)
        temporary.rename(archive)
    with archive.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    if digest!=SHA256:raise ValueError(f'Archive checksum mismatch: {archive}')
    destination=output/'extracted'
    executable=destination/'Blocks/Binaries/Linux/Blocks-Linux-Shipping'
    if not destination.exists():
        with zipfile.ZipFile(archive) as bundle:
            for item in bundle.infolist():
                name=Path(item.filename)
                if name.is_absolute() or '..' in name.parts or stat.S_ISLNK(item.external_attr>>16):
                    raise ValueError('Unsafe archive entry')
            bundle.extractall(destination)
    if not executable.is_file():raise ValueError('Incomplete extraction; use a new output directory')
    executable.chmod(executable.stat().st_mode|stat.S_IXUSR)
    return executable


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('.deps/blocks-linux-1.0.1'))
    args=parser.parse_args();print(prepare(args.output))
