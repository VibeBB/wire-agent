"""The VibeBB producer mark printed in the sheet frame.

Geometry is the ``silkscreen`` group of ``assets/vibebb-silkscreen.svg`` in
VibeBB/www.vibebb.org (commit 2ad2267), recoloured black for paper with the
board-preview plate dropped. It is pure stroke geometry (no text or fonts),
so it renders identically wherever the drawing is opened.
"""

from __future__ import annotations

import base64

__all__ = ["MARK_ASPECT", "MARK_SVG", "mark_data_uri"]

MARK_ASPECT = 40.0 / 18.0  # viewBox width / height

MARK_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 18" width="40mm" height="18m'
    'm"><g id="silkscreen" fill="none" stroke="#000000" stroke-linecap="square" stroke-li'
    'nejoin="miter"><path d="M4.2 1 H39 V13.8 L35.8 17 H1 V4.2 Z" stroke-width="0.6"/><g '
    'stroke-width="0.45"><path d="M36.9 2.3 H37.7 V4.4"/><path d="M3.1 15.7 H2.3 V13.6"/>'
    '</g><path d="M4 3 H19.6 l1.4 -1.4 H30.4" stroke-width="0.4"/><g fill="#000000" strok'
    'e="none"><rect x="3.6" y="2.6" width="0.8" height="0.8"/><rect x="30.2" y="1.2" widt'
    'h="0.8" height="0.8"/></g><g stroke-width="0.75"><path d="M4.5 6 L6.5 12 L8.5 6"/><p'
    'ath d="M10.2 8 V12"/><path d="M12 5 V12"/><path d="M12 8 H15.4 L16.4 9 V11 L15.4 12 '
    'H12"/><path d="M21.2 11 L20.4 12 H18.2 L17.4 11 V9 L18.2 8 H20.4 L21.2 9 V10 H17.4"/'
    '><path d="M22.4 6 V12"/><path d="M22.4 6 H25.8 L26.8 7 V8 L25.8 9 H22.4"/><path d="M'
    '22.4 9 H25.8 L26.8 10 V11 L25.8 12 H22.4"/><path d="M27.8 6 V12"/><path d="M27.8 6 H'
    '31.2 L32.2 7 V8 L31.2 9 H27.8"/><path d="M27.8 9 H31.2 L32.2 10 V11 L31.2 12 H27.8"/'
    '></g><rect x="9.6" y="6" width="1.2" height="1.2" fill="#000000" stroke="none"/><g s'
    'troke-width="0.5"><path d="M33.6 6.6 H37.4"/><path d="M34.8 8.6 H37.4"/><path d="M33'
    '.6 10.6 H36.2"/></g><g stroke-width="0.45"><path d="M4 15.6 V14.2"/><path d="M5.4 15'
    '.6 V13.4"/><path d="M6.8 15.6 V14.6"/><path d="M8.2 15.6 V13.4"/><path d="M9.6 15.6 '
    'V14.6"/><path d="M11 15.6 V14.2"/><path d="M12.4 15.6 V13.4"/><path d="M13.8 15.6 V1'
    '4.6"/><path d="M15.2 15.6 V14.2"/><path d="M16.6 15.6 V13.4"/><path d="M18 15.6 V14.'
    '6"/><path d="M19.4 15.6 V14.2"/><path d="M20.8 15.6 V13.4"/><path d="M22.2 15.6 V14.'
    '6"/><path d="M23.6 15.6 V14.2"/><path d="M25 15.6 V13.4"/><path d="M26.4 15.6 V14.6"'
    '/><path d="M27.8 15.6 V14.2"/><path d="M29.2 15.6 V13.4"/><path d="M30.6 15.6 V14.6"'
    '/><path d="M32 15.6 V14.2"/></g></g></svg>'
)


def mark_data_uri() -> str:
    """drawio image reference (drawio styles cannot carry ``;base64``)."""
    return "data:image/svg+xml," + base64.b64encode(MARK_SVG.encode("utf-8")).decode("ascii")
