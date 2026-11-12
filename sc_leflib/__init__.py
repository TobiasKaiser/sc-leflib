import logging

from ._leflib import parse as _parse
from ._leflib import LefParseError

try:
    from sc_leflib._version import __version__
except ImportError:
    __version__ = None

__all__ = ['parse', 'LefParseError']

# Warnings and info messages from the LEF parser are logged to the 'sc_leflib'
# logger. As recommended for libraries, nothing is printed unless the
# application configures logging.
logging.getLogger(__name__).addHandler(logging.NullHandler())


def parse(path):
    ''' Parses LEF file.

    Given a path to a LEF file, this function parses the file and returns a
    dictionary representing the contents of the LEF file.

    The file is opened with Python's :func:`open`, so failing to open or read
    it raises the same :class:`OSError` subclass that :func:`open` would raise
    (e.g. :class:`FileNotFoundError`, :class:`PermissionError` or
    :class:`IsADirectoryError`), with ``errno``, ``strerror`` and ``filename``
    set. If the LEF parser rejects the file, :class:`LefParseError` is raised.
    It carries the parser's message, the file name and, where available, the
    line number.

    Nothing is printed to stdout or stderr. Warnings and informational
    messages from the parser are sent to the ``sc_leflib`` logger (see
    :mod:`logging`) at ``WARNING`` and ``INFO`` level. Each log record has the
    extra attributes ``lef_filename``, ``lef_lineno`` and ``lef_code`` (the
    parser's message number, the ``n`` in ``LEFPARS-n``). Errors that the
    parser reports without rejecting the file are logged at ``ERROR`` level.
    The ``sc_leflib`` logger has a :class:`logging.NullHandler`, so these
    messages are only shown if the application configures logging, e.g. with
    :func:`logging.basicConfig`.

    .. versionchanged:: 0.6
        Errors raise exceptions instead of returning ``None``, and messages
        go to the ``sc_leflib`` logger instead of stdout/stderr.
        ``os.PathLike`` paths are accepted.

    Note that this function does not return all information contained in the
    LEF. The subset of information returned includes:

    * LEF version
    * Bus bit characters
    * Divider characters
    * Units
    * Manufacturing grid
    * Use min spacing
    * Clearance measure
    * Fixed mask
    * Layer information

        * Type
        * Width
        * Direction
        * Offset
        * Pitch

    * Max stack via
    * Viarules
    * Sites
    * Macro information

        * Size
        * Pins
        * Obstructions

    The dictionary returned by this function is designed to mimic the structure
    of the LEF file as closely as possible, and this function does minimal
    legality checking. The order all top-level objects appear in the dictionary
    is guaranteed to match the LEF file. It looks like follows:

        .. code-block:: python

            {
                'version': 5.8,
                'busbitchars': '<>',
                'dividerchar': ':',
                'units': {
                    'capacitance': 10.0,
                    'current': 10000.0,
                    'database': 20000.0,
                    'frequency': 10.0,
                    'power': 10000.0,
                    'resistance': 10000.0,
                    'time': 100.0,
                    'voltage': 1000.0
                },
                'manufacturinggrid': 0.05,
                'useminspacing': {'OBS': 'OFF'},
                'clearancemeasure': 'MAXXY',
                'fixedmask': True,
                'layers': {
                    'M1': {
                        'type': 'ROUTING',
                        'direction': 'HORIZONTAL',
                        'offset': (0.1, 0.2),
                        'pitch': 1.8,
                        'width': 1.0
                    },
                    'V1': {
                        'type': 'CUT',
                    },
                    ...
                },
                'maxviastack': {'range': {'bottom': 'm1', 'top': 'm7'}, 'value': 4},
                'viarules': {
                    '<name>': {
                        'generate': True,
                        'layers': [
                            {'enclosure': {'overhang1': 1.4,
                                           'overhang2': 1.5},
                             'name': 'M1',
                             'width': {'max': 19.0, 'min': 0.1}},
                            {'enclosure': {'overhang1': 1.4,
                                           'overhang2': 1.5},
                             'name': 'M2',
                             'width': {'max': 1.9, 'min': 0.2}},
                            {'name': 'M3',
                             'rect': (-0.3, -0.3, -0.3, 0.3),
                             'resistance': 0.5,
                             'spacing': {'x': 5.6, 'y': 7.0}}
                        ]
                    },
                    '<name>': {
                        {'layers': [
                            {'direction': 'VERTICAL',
                             'name': 'M1',
                             'width': {'max': 9.6, 'min': 9.0}},
                             {'direction': 'HORZIONTAL',
                             'name': 'M1',
                             'width': {'max': 3.0, 'min': 3.0}}
                        ]}
                    },
                    ...
                }
                'macros': {
                    '<name>': {
                        'size': {
                            'width': 5,
                            'height': 8
                        },
                        'pins': {
                            '<name>': {
                                'ports': [{
                                    'class': 'CORE',
                                    'layer_geometries': [{
                                        'layer': 'M1',
                                        'exceptpgnet': True,
                                        'spacing': 0.01,
                                        'designrulewidth': 0.05,
                                        'width': 1.5,
                                        'shapes': [
                                            {
                                                'rect': (0, 0, 5, 5),
                                                'mask': 1,
                                                'iterate': {
                                                    'num_x': 2,
                                                    'num_y': 3,
                                                    'space_x': 1,
                                                    'space_y': 4
                                                }
                                            },
                                            {
                                                'path': [(0, 0), (5, 0), (0, 5)],
                                                'iterate': ...
                                            },
                                            {
                                                'polygon': [(0, 0), (5, 0), (0, 5)],
                                                'iterate': ...
                                            }
                                        ],
                                        'via': {
                                            'pt': (2, 3),
                                            'name': 'via1',
                                            'iterate': ...
                                        }
                                    }]
                                }]
                            },
                            ...
                        }
                    },
                    ...
                }
            }

    If some entry is not specified in the LEF, the corresponding key will not be
    present in the dictionary.

    Args:
        path (str, bytes or os.PathLike): Path to LEF file to parse.

    Returns:
        dict: Contents of the LEF file, as described above.

    Raises:
        OSError: If the file can't be opened or read. The subclass and
            attributes match what :func:`open` raises.
        LefParseError: If the LEF parser rejects the file (e.g. because of a
            syntax error).
        TypeError: If ``path`` is not a str, bytes or os.PathLike object.
    '''

    return _parse(path)
