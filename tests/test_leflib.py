import errno
import logging
import os
import pathlib
import pickle
import sys

import pytest

import sc_leflib


MALFORMED_LEF = """VERSION 5.8 ;
MACRO foo
  garbage here ;;
END bar
"""

GOOD_LEF = """VERSION 5.8 ;
MACRO foo
  SIZE 1 BY 2 ;
END foo
END LIBRARY
"""


def expected_open_error(path):
    '''Returns the exception Python's open() raises for path.'''
    try:
        open(path, 'rb').close()
    except OSError as e:
        return e
    pytest.fail(f'open({path!r}) unexpectedly succeeded')


def assert_matches_open_error(error, path):
    expected = expected_open_error(path)
    assert type(error) is type(expected)
    assert error.errno == expected.errno
    assert error.strerror == expected.strerror
    assert error.filename == expected.filename


def test_leflib_missing_file(tmp_path, capfd):
    path = str(tmp_path / 'does_not_exist.lef')
    with pytest.raises(FileNotFoundError) as excinfo:
        sc_leflib.parse(path)

    assert excinfo.value.errno == errno.ENOENT
    assert excinfo.value.filename == path
    assert_matches_open_error(excinfo.value, path)
    assert capfd.readouterr() == ('', '')


@pytest.mark.skipif(sys.platform == 'win32' or os.geteuid() == 0,
                    reason='file permissions are not enforced')
def test_leflib_unreadable_file(tmp_path, capfd):
    path = tmp_path / 'unreadable.lef'
    path.write_text(GOOD_LEF)
    path.chmod(0)
    try:
        with pytest.raises(PermissionError) as excinfo:
            sc_leflib.parse(str(path))

        assert excinfo.value.errno == errno.EACCES
        assert excinfo.value.filename == str(path)
        assert_matches_open_error(excinfo.value, str(path))
    finally:
        path.chmod(0o600)
    assert capfd.readouterr() == ('', '')


def test_leflib_directory(tmp_path, capfd):
    # IsADirectoryError on POSIX, PermissionError on Windows: same as open().
    with pytest.raises(OSError) as excinfo:
        sc_leflib.parse(str(tmp_path))

    assert_matches_open_error(excinfo.value, str(tmp_path))
    assert capfd.readouterr() == ('', '')


@pytest.mark.skipif(not sys.platform.startswith('linux'),
                    reason='needs /proc/self/mem')
def test_leflib_read_error():
    # /proc/self/mem can be opened, but reading at offset 0 fails with EIO.
    with pytest.raises(OSError) as excinfo:
        sc_leflib.parse('/proc/self/mem')
    assert excinfo.value.errno == errno.EIO


def test_leflib_malformed_file(tmp_path, capfd):
    path = tmp_path / 'bad.lef'
    path.write_text(MALFORMED_LEF)

    with pytest.raises(sc_leflib.LefParseError) as excinfo:
        sc_leflib.parse(str(path))

    error = excinfo.value
    assert isinstance(error, ValueError)
    assert error.filename == str(path)
    assert error.lineno == 3
    assert error.code == 1
    assert 'garbage' in error.msg
    assert str(error) == error.msg
    assert error.errors == [error.msg]
    # Diagnostics go into the exception instead of stdout/stderr.
    assert capfd.readouterr() == ('', '')


def test_leflib_multiple_errors(tmp_path):
    path = tmp_path / 'nonascii.lef'
    path.write_bytes(GOOD_LEF.replace('foo', 'f\u00f6o').encode('utf-8'))

    with pytest.raises(sc_leflib.LefParseError) as excinfo:
        sc_leflib.parse(path)

    error = excinfo.value
    assert error.lineno == 2
    assert error.code == 1008
    assert len(error.errors) == 2
    assert error.errors[0] == error.msg


def test_leflib_parse_error_pickle():
    error = sc_leflib.LefParseError('msg', filename='a.lef', lineno=3, code=1,
                                    errors=['msg', 'other'])
    copy = pickle.loads(pickle.dumps(error))
    assert type(copy) is sc_leflib.LefParseError
    assert (copy.msg, copy.filename, copy.lineno, copy.code, copy.errors) == \
        ('msg', 'a.lef', 3, 1, ['msg', 'other'])


def test_leflib_pathlike(tmp_path):
    path = tmp_path / 'g\u00f6\u00f6d.lef'
    path.write_text(GOOD_LEF)

    expected = {'version': 5.8, 'macros': {'foo': {'size': {'width': 1, 'height': 2}}}}
    assert sc_leflib.parse(path) == expected
    assert sc_leflib.parse(pathlib.PurePath(path)) == expected
    assert sc_leflib.parse(os.fsencode(path)) == expected


def test_leflib_invalid_path_type():
    with pytest.raises(TypeError):
        sc_leflib.parse(3)


def test_leflib_warnings_logged(datadir, caplog, capfd):
    path = os.path.join(datadir, 'complete.5.8.lef')
    with caplog.at_level(logging.INFO, logger='sc_leflib'):
        assert sc_leflib.parse(path)

    # Warnings go to the logger only, never directly to stdout/stderr.
    assert capfd.readouterr() == ('', '')

    records = [r for r in caplog.records if r.name == 'sc_leflib']
    assert records
    assert all(r.levelno == logging.WARNING for r in records)
    assert all(r.lef_filename == path for r in records)

    first = records[0]
    assert first.lef_code == 2009
    assert first.lef_lineno == 8
    assert 'USEMINSPACING PIN' in first.getMessage()


def test_leflib_complete(datadir):
    # This file contains nonsense and some things that are technically illegal,
    # but good coverage of what you might see in a LEF. I've left comments where
    # the contents of `data` don't perfectly match the LEF contents, with
    # explanations as to why.
    path = os.path.join(datadir, 'complete.5.8.lef')
    data = sc_leflib.parse(path)

    assert data['version'] == 5.8
    assert data['fixedmask'] is True
    # There's a "USEMINSPACING PIN" statement, but it gets skipped since it's
    # obsolete syntax in 5.8
    assert data['useminspacing'] == {'OBS': 'OFF'}
    # There are two CLEARANCEMEASURE statements, we only take the second one
    assert data['clearancemeasure'] == 'MAXXY'
    assert data['busbitchars'] == '<>'
    assert data['dividerchar'] == ':'
    assert data['units'] == {
        'capacitance': 10.0,
        'current': 10000.0,
        'database': 20000.0,
        'frequency': 10.0,
        'power': 10000.0,
        'resistance': 10000.0,
        'time': 100.0,
        'voltage': 1000.0
    }
    assert data['manufacturinggrid'] == 3.5

    assert len(data['layers']) == 26
    assert data['layers']['POLYS']['type'] == 'MASTERSLICE'

    cut01 = data['layers']['CUT01']
    assert cut01['type'] == 'CUT'
    assert cut01['offset'] == (0.5, 0.6)
    assert cut01['pitch'] == (1.2, 1.3)

    rx = data['layers']['RX']
    assert rx['type'] == 'ROUTING'
    assert rx['pitch'] == 1.8
    assert rx['offset'] == 0.9
    assert rx['width'] == 1
    assert rx['direction'] == 'HORIZONTAL'

    assert data['maxviastack'] == {'value': 4, 'range': {'bottom': 'm1', 'top': 'm7'}}
    assert data

    # 11 viarules defined, but two are skipped because they are "turn-vias"
    # (obsolete in 5.8)
    assert len(data['viarules']) == 9

    vialist12 = data['viarules']['VIALIST12']
    assert len(vialist12['layers']) == 2
    assert vialist12['layers'][0] == {
        'name': 'M1',
        'direction': 'VERTICAL',
        'width': {'min': 9.0, 'max': 9.6}
    }
    assert vialist12['layers'][1] == {
        'name': 'M2',
        'direction': 'HORIZONTAL',
        'width': {'min': 3.0, 'max': 3.0}
    }
    assert vialist12['vias'] == ['VIACENTER12']

    via12 = data['viarules']['via12']
    assert via12['generate'] is True
    assert via12['default'] is True

    assert len(via12['layers']) == 3
    assert via12['layers'][0] == {
        'name': 'm1',
        'enclosure': {'overhang1': 0.03, 'overhang2': 0.01}
    }
    assert via12['layers'][1] == {
        'name': 'm2',
        'enclosure': {'overhang1': 0.05, 'overhang2': 0.01}
    }
    assert via12['layers'][2] == {
        'name': 'cut12',
        'spacing': {'x': 0.4, 'y': 0.4},
        'rect': (-0.1, -0.1, 0.1, 0.1),
        'resistance': 20
    }

    assert len(data['sites']) == 10
    cover = data['sites']['COVER']
    assert cover['class'] == 'PAD'
    assert cover['symmetry'] == ['R90']
    assert cover['size'] == {'width': 10, 'height': 10}

    assert len(data['macros']) == 14
    chk3a = data['macros']['CHK3A']
    assert chk3a['size'] == {'width': 10.8, 'height': 28.8}
    assert len(chk3a['pins']) == 7
    vdd = chk3a['pins']['VDD']
    assert vdd['direction'] == "INOUT"
    assert vdd['use'] == "POWER"
    assert len(vdd['ports']) == 2
    port = vdd['ports'][1]
    assert port['class'] == 'NONE'
    assert len(port['layer_geometries']) == 1
    geo = port['layer_geometries'][0]
    assert geo['layer'] == 'M1'
    assert geo['shapes'] == [{
        'rect': (-0.9, 21, 9.9, 24),
        'mask': 0,
        'iterate': {
            'num_x': 1,
            'num_y': 2,
            'step_x': 1,
            'step_y': 1
        }
    }]

    assert len(chk3a['obs']) == 1
    obs = chk3a['obs'][0][0]
    assert obs['layer'] == 'M1'
    assert obs['spacing'] == 5.6
    assert len(obs['shapes']) == 10
    assert obs['shapes'][0] == {
        'rect': (6.6, -0.6, 9.6, 0.6),
        'mask': 0
    }
