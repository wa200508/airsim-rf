"""Install a wheel separately while sharing the current interpreter's tested dependencies.

This CI check is offline. Full clean dependency installation is a separate gate.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import sysconfig
import tempfile
import venv


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='airsim-rf-wheel-') as directory:
        environment=Path(directory)
        venv.EnvBuilder(with_pip=True).create(environment)
        python=environment/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
        purelib=Path(subprocess.check_output([str(python),'-c',
            'import sysconfig; print(sysconfig.get_paths()["purelib"])'],text=True).strip())
        # Nested venvs do not automatically inherit the creating venv's site.
        dependencies=sysconfig.get_paths()['purelib']
        (purelib/'qualified-dependencies.pth').write_text(f'import site; site.addsitedir({dependencies!r})\n')
        subprocess.run([str(python),'-m','pip','install','--ignore-installed','--no-deps','--no-index',
                        str(args.wheel.resolve())],check=True)
        subprocess.run([str(python),str(Path(__file__).with_name('qualify_installed_package.py')),
                        '--output',str(args.output.resolve())],cwd=directory,check=True)


if __name__=='__main__':
    main()
