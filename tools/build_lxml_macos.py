"""Build and validate isolated lxml/XML/XSLT candidates using macOS iconv.

The default validation-only CLI fails closed without writes; --build explicitly
creates an unsigned local wheel. Evidence is NOT frozen-app legal clearance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tarfile
import urllib.request


def build_environment(prefix: Path, inherited: dict) -> dict:
    # An SDK-header fallback can appear successful but compile the wrong XML ABI.
    env = {k: v for k, v in inherited.items() if k not in {
        'STATICBUILD', 'STATIC_DEPS', 'CFLAGS', 'CPPFLAGS', 'CXXFLAGS', 'LDFLAGS',
        'CPATH', 'LIBRARY_PATH', 'DYLD_LIBRARY_PATH', 'DYLD_INSERT_LIBRARIES',
        'XML2_CONFIG', 'XSLT_CONFIG', 'INCLUDE', 'LIBRARY', 'SDKROOT'}}
    env.update({'MACOSX_DEPLOYMENT_TARGET': '12.0',
                'CFLAGS': '-O2 -arch arm64 -mmacosx-version-min=12.0',
                'CPPFLAGS': f'-I{prefix / "include"} -I{prefix / "include/libxml2"}',
                'LDFLAGS': '-arch arm64 -mmacosx-version-min=12.0',
                'INCLUDE': f'{prefix / "include"} {prefix / "include/libxml2"}',
                'LIBRARY': str(prefix / 'lib'),
                'XML2_CONFIG': str(prefix / 'bin/xml2-config'),
                'XSLT_CONFIG': str(prefix / 'bin/xslt-config')})
    return env


def inspect_native(path: Path) -> dict:
    links = subprocess.check_output(['otool', '-L', str(path)], text=True)
    symbols = subprocess.check_output(['nm', '-a', str(path)], text=True)
    if re.search(r' [TtDd] _+libiconv_(?:open|version)\b', symbols):
        raise ValueError('Static GNU iconv detected')
    linked = sorted(line.strip().split(' (compatibility')[0]
                    for line in links.splitlines() if line.startswith('\t'))
    if '/usr/lib/libiconv.2.dylib' not in linked:
        raise ValueError('Expected dynamic macOS iconv is missing')
    if any(not link.startswith('/usr/lib/') for link in linked):
        raise ValueError('Unexpected non-system dynamic dependency')
    return {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'linked_libraries': linked, 'static_iconv_symbols': False}


def validate_versions(result: dict) -> None:
    for key, expected in {'xml_runtime': [2, 15, 2], 'xml_compiled': [2, 15, 2],
                          'xslt_runtime': [1, 1, 45], 'xslt_compiled': [1, 1, 45]}.items():
        if result.get(key) != expected:
            raise ValueError(f'Unexpected {key} version; refusing SDK-header/library fallback')


def extract_verified(archive: Path, digest: str, destination: Path) -> Path:
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise ValueError('Source SHA-256 mismatch')
    with tarfile.open(archive) as stream:
        members = stream.getmembers()
        for member in members:
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                raise ValueError('Unsafe source archive member')
        destination.mkdir()
        stream.extractall(destination, filter='data')
    roots = list(destination.iterdir())
    if len(roots) != 1 or not roots[0].is_dir():
        raise ValueError('Expected one upstream source directory')
    return roots[0]


SOURCES = {
    'libxml2': ('https://download.gnome.org/sources/libxml2/2.15/libxml2-2.15.2.tar.xz',
                'c8b9bc81f8b590c33af8cc6c336dbff2f53409973588a351c95f1c621b13d09d'),
    'libxslt': ('https://download.gnome.org/sources/libxslt/1.1/libxslt-1.1.45.tar.xz',
               '9acfe68419c4d06a45c550321b3212762d92f41465062ca4ea19e632ee5d216e'),
    'lxml': ('https://files.pythonhosted.org/packages/23/ad/28ecd7cb894d172f3c9c80a075eeeb2017ac62e3632cee05a5f9493547eb/lxml-6.1.3.tar.gz',
             '45222d94ddd511536f3b2f7d9deae3b2339b4ce0f075f1ca25703b07cad9dd21'),
}


def build_candidate(work: Path) -> dict:
    """Build only a candidate wheel; never install into the product environment."""
    import shutil
    import zipfile
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise RuntimeError('Native candidate requires macOS arm64')
    if work.exists() or work.is_symlink():
        raise ValueError('A fresh workspace is required')
    work = work.absolute()
    if any(c.isspace() or c in "'\"$`;\\" for c in str(work)):
        raise ValueError('Workspace must not contain shell metacharacters or whitespace')
    for tool in ('make', 'clang', 'xcrun', 'otool', 'nm', 'pkg-config'):
        if shutil.which(tool) is None:
            raise RuntimeError(f'Required native tool missing: {tool}')
    work.mkdir(mode=0o700, parents=True)
    prefix = work / 'prefix'
    env = build_environment(prefix, {'PATH': os.defpath + ':' + str(Path(shutil.which('pkg-config')).parent),
                                     'HOME': str(work / 'home'), 'TMPDIR': str(work)})
    env.update({'CC': '/usr/bin/clang', 'PKG_CONFIG_LIBDIR': str(prefix / 'lib/pkgconfig'),
                'PKG_CONFIG_PATH': str(prefix / 'lib/pkgconfig'),
                'LDFLAGS': env['LDFLAGS'] + f' -L{prefix / "lib"}',
                'CXXFLAGS': '-O2 -arch arm64 -mmacosx-version-min=12.0'})
    (work / 'home').mkdir()
    report = {'release_ready': False, 'publication_blocked': True, 'status': 'building',
              'sources': {}, 'commands': [], 'python': sys.version, 'environment': env,
              'remaining_gates': ['exact frozen artifact reconciliation', 'full native/license review',
                                  'Developer ID/notarization', 'parent integration approval']}
    evidence = work / 'evidence.json'
    def save():
        evidence.write_text(json.dumps(report, indent=2) + '\n')
    def run(command, cwd):
        entry = {'argv': list(map(str, command)), 'cwd': str(cwd)}
        report['commands'].append(entry)
        save()
        with (work / 'build.log').open('a') as log:
            result = subprocess.run(entry['argv'], cwd=cwd, env=env, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=240)
        entry['returncode'] = result.returncode
        save()
        result.check_returncode()
    save()
    try:
        roots = {}
        for name, (url, digest) in SOURCES.items():
            archive = work / url.rsplit('/', 1)[1]
            with urllib.request.urlopen(url, timeout=45) as response:
                if not response.geturl().startswith('https://'):
                    raise ValueError('Refusing insecure source redirect')
                archive.write_bytes(response.read(32 * 1024 * 1024 + 1))
            roots[name] = extract_verified(archive, digest, work / (name + '-source'))
            report['sources'][name] = {'url': url, 'sha256': digest, 'archive': str(archive)}
            save()
        run([roots['libxml2'] / 'configure', f'--prefix={prefix}', '--disable-shared',
             '--enable-static', '--without-python', '--with-iconv', '--with-zlib', '--with-schematron'], roots['libxml2'])
        run(['make', '-j4'], roots['libxml2'])
        run(['make', 'install'], roots['libxml2'])
        run([roots['libxslt'] / 'configure', f'--prefix={prefix}', '--disable-shared',
             '--enable-static', '--without-python', f'--with-libxml-prefix={prefix}'], roots['libxslt'])
        run(['make', '-j4'], roots['libxslt'])
        run(['make', 'install'], roots['libxslt'])
        env['LDFLAGS'] += ' -liconv'
        run([sys.executable, 'setup.py', '--without-cython',
             '--with-xml2-config', prefix / 'bin/xml2-config',
             '--with-xslt-config', prefix / 'bin/xslt-config', 'bdist_wheel'], roots['lxml'])
        wheels = list((roots['lxml'] / 'dist').glob('*.whl'))
        if len(wheels) != 1:
            raise ValueError('Expected exactly one candidate wheel')
        candidate = work / 'candidate'
        with zipfile.ZipFile(wheels[0]) as archive:
            archive.extractall(candidate)
        natives = sorted((candidate / 'lxml').glob('*.so'))
        if not any(p.name.startswith('etree.') for p in natives) or not any(p.name.startswith('objectify.') for p in natives):
            raise ValueError('Required lxml modules missing')
        report['native'] = [inspect_native(path) for path in natives if path.name.startswith(('etree.', 'objectify.'))]
        probe = work / 'probe.py'
        probe.write_text('''import io, json, sys
from pathlib import Path
sys.path[:0] = [sys.argv[1], sys.argv[2]]
from lxml import etree, objectify
from docx import Document
from knowledge_hub.intake_extractors import _extract
assert Path(etree.__file__).is_relative_to(Path(sys.argv[1]))
assert {'catalog', 'html', 'iconv', 'regexp', 'schematron', 'xmlschema', 'xpath', 'zlib'} <= etree.LIBXML_FEATURES
assert objectify.fromstring(b'<n>7</n>').pyval == 7
xslt = etree.XSLT(etree.XML(b'<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform"><xsl:template match="/"><ok/></xsl:template></xsl:stylesheet>'))
assert xslt(etree.XML(b'<root/>')).getroot().tag == 'ok'
assert etree.fromstring(b'<?xml version="1.0" encoding="ISO-8859-1"?><r>caf\\xe9</r>').text == 'café'
doc = Document()
doc.add_paragraph('Synthetic native DOCX — café ภาษาไทย')
doc.add_table(rows=1, cols=1).cell(0, 0).text = 'Table preserved'
data = io.BytesIO()
doc.save(data)
result = _extract(data.getvalue(), 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
assert result == {'status': 'extracted', 'text': 'Synthetic native DOCX — café ภาษาไทย\\nTable preserved'}, result
print(json.dumps({'xml_runtime': etree.LIBXML_VERSION, 'xml_compiled': etree.LIBXML_COMPILED_VERSION, 'xslt_runtime': etree.LIBXSLT_VERSION, 'xslt_compiled': etree.LIBXSLT_COMPILED_VERSION, 'docx': result, 'etree_file': etree.__file__, 'objectify_file': objectify.__file__}))
''')
        command = [sys.executable, str(probe), str(candidate), str(Path(__file__).resolve().parents[1] / 'src')]
        report['probe_command'] = command
        output = subprocess.check_output(command, cwd=work, env=env, text=True, timeout=20)
        report['probe'] = json.loads(output)
        validate_versions(report['probe'])
        report['wheel'] = {'file': str(wheels[0]), 'sha256': hashlib.sha256(wheels[0].read_bytes()).hexdigest()}
        report['status'] = 'candidate-verified-not-release-cleared'
        save()
        return report
    except Exception as error:
        report.update(status='blocked', error=f'{type(error).__name__}: {error}')
        save()
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True, help='Fresh scratch workspace')
    parser.add_argument('--build', action='store_true', help='Explicitly build an isolated candidate, never a release')
    args = parser.parse_args(argv)
    if args.work.exists() or args.work.is_symlink():
        raise ValueError('A fresh workspace is required')
    if not args.build:
        raise RuntimeError('Native dependency build is not implemented in validation-only mode; binary release remains blocked (use --build for a candidate)')
    report = build_candidate(args.work)
    if report.get('release_ready') is not False or report.get('publication_blocked') is not True:
        raise ValueError('Candidate cannot clear publication gates')
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    main()
