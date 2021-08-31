from datetime import datetime
from multiprocessing import Process
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union, cast

from .csv import selector

MARGIN = 0.2


class BackgroundProcessor(Process):
    """Offers a way to compute - in a background process - all data needed by pyqtgraph
    from pyqtgraph visible range.

    The main (caller) process can communicate with the background process through a
    pipe.

    If several items a present in the pipe, then `BackgroundSelector` will process only
    the last one.

    Send `None` to the pipe to stop `BackgroundSelector`

    Usage:
    ------
    connection, background_connection = Pipe()

    background_processor = BackgroundProcessor(
        dir_path, ("a", int), ["b", "d"], 100, background_connection
    )

    background_processor.start()

    connection.send((None, None))
    connection.recv() == (
        [1, 5, 9, 13, 17],
        {
            "b": Selected.Y(mins=[2, 6, 10, 14, 18], maxs=[2, 6, 10, 14, 18]),
            "d": Selected.Y(mins=[4, 8, 12, 16, 20], maxs=[4, 8, 12, 16, 20]),
        }
    )

    connection.send(4.5, 13.5) == (
        [5, 9, 13],
        {
            "b": Selected.Y(mins=[6, 10, 14], maxs=[6, 10, 14]),
            "d": Selected.Y(mins=[8, 12, 16], maxs=[8, 12, 16]),
        }
    )

    connection.send(None)
    """

    def __init__(
        self,
        dir_path: Path,
        x_and_type: Tuple[str, type],
        ys: List[str],
        resolution: int,
        connection: Connection,
    ) -> None:
        """Initializer

        dir_path  : Directory where all the files (sampled and non sampled) are located.
                    Non sampled path name's HAS to be `0.csv`

        x_and_type: Name and the type of X value
        ys        : Name of Ys types
        resolution: Resolution to be as close as possible
        connection: One side of the pipe
        """
        super().__init__()
        self.__dir_path = dir_path
        self.__x_and_type = x_and_type
        self.__ys = ys
        self.__resolution = resolution
        self.__connection = connection

    def run(self) -> None:
        with selector(
            self.__dir_path,
            self.__x_and_type,
            [(y, float) for y in self.__ys],
            self.__resolution,
        ) as sel:
            while True:
                item: Optional[
                    Tuple[
                        Optional[float],
                        Optional[float],
                    ]
                ] = self.__connection.recv()

                if item is None:
                    self.__connection.send(None)
                    return

                while self.__connection.poll():
                    item = self.__connection.recv()

                    if item is None:
                        self.__connection.send(None)
                        return

                visible_start_float, visible_stop_float = item

                assert not (visible_start_float is None) != (
                    visible_stop_float is None
                ), (
                    "`visible_start_float` and `visible_stop_float` must be both set "
                    "to None or set to a value which is not None"
                )

                if visible_start_float is None and visible_stop_float is None:
                    selected = sel[:]
                elif visible_start_float is not None and visible_stop_float is not None:
                    visible_range = visible_stop_float - visible_start_float
                    visible_range_with_margin = MARGIN * visible_range

                    start_float = visible_start_float - visible_range_with_margin
                    stop_float = visible_stop_float + visible_range_with_margin

                    start = datetime.fromtimestamp(start_float)
                    stop = datetime.fromtimestamp(stop_float)

                    selected = sel[start:stop]  # type: ignore
                else:
                    raise ValueError(
                        "`visible_start_float` and `visible_stop_float` must be both "
                        "set to None or set to a value which is not None"
                    )

                first_x, *_ = selected.xs

                xs = (
                    [x.timestamp() for x in cast(List[datetime], selected.xs)]
                    if isinstance(first_x, datetime)
                    else cast(List[float], selected.xs)
                )

                self.__connection.send((xs, selected.name_to_y))