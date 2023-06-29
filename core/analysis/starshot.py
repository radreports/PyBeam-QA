from PySide6.QtWidgets import QSizePolicy
from PySide6.QtCore import Signal, Slot, QObject

import io
import traceback
import pyqtgraph as pg
import numpy as np
from typing import BinaryIO, Optional, Union
from pylinac.core.geometry import Point
from pylinac.starshot import Starshot

class QStarshot(Starshot):

    def __init__(self, filepath: str | BinaryIO, **kwargs):
        super().__init__(filepath, **kwargs)

        self.imagePlotWidget = pg.PlotWidget()
        self.imagePlotWidget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.imagePlotWidget.setFixedSize(600, 400)
        self.imagePlotWidget.setAspectLocked(lock=True)

    def analyze(self, 
                radius: float = 0.85,
                min_peak_height: float = 0.25,
                tolerance: float = 1,
                start_point: Point | tuple | None = None,
                fwhm: bool = True,
                recursive: bool = True,
                invert: bool = False):
        
        return super().analyze(radius, min_peak_height, tolerance, start_point, fwhm, recursive, invert)
    
    def plotImage(self):
        # plot the image
        self.imagePlotWidget.addItem(pg.ImageItem(self.image.array))

        self.imagePlotWidget.setLimits(xMin = -self.image.shape[1] * 0.5, xMax = self.image.shape[1] * 1.5,
                                       yMin = -self.image.shape[0] * 0.5, yMax = self.image.shape[0] * 1.5) 

        # plot the lines
        for line in self.lines:
            self.imagePlotWidget.plot(x = [line.point1.x, line.point2.x],
                                      y = [line.point1.y, line.point2.y],
                                      pen = pg.mkPen((255,0,255), width=1.5))
            
        # plot the circle profile
        width_ratio = self.circle_profile.width_ratio
        radius = self.circle_profile.radius
        center_x = self.circle_profile.center.x
        center_y = self.circle_profile.center.y
        x_outer = radius * (1 + width_ratio) * np.cos(np.linspace(0, 2*np.pi, 1000)) + center_x
        y_outer = radius * (1 + width_ratio) * np.sin(np.linspace(0, 2*np.pi, 1000)) + center_y
        self.imagePlotWidget.plot(x_outer, y_outer, pen = pg.mkPen((0, 255, 0), width = 2))

        x_outer = radius * (1 - width_ratio) * np.cos(np.linspace(0, 2*np.pi, 1000)) + center_x
        y_outer = radius * (1 - width_ratio) * np.sin(np.linspace(0, 2*np.pi, 1000)) + center_y

        self.imagePlotWidget.plot(x_outer, y_outer, pen = pg.mkPen((0, 255, 0), width = 2))

        # plot the wobble

        self.imagePlotWidget.addItem(
            pg.ScatterPlotItem([self.wobble.center.x], [self.wobble.center.y],
                           pen = pg.mkPen(None), brush = pg.mkBrush(0, 0, 200, 150),
                           size = self.wobble.diameter, pxMode = False))

        # plot the peaks
        peaks = self.circle_profile.peaks

        peak_x = [peak.x for peak in peaks]
        peak_y = [peak.y for peak in peaks]

        self.imagePlotWidget.addItem(pg.ScatterPlotItem(peak_x, peak_y,
                                                        size = 15, pxMode = False,
                                                        pen = pg.mkPen(None), brush = pg.mkBrush(255,0,255, 150)))
        

    def get_publishable_plots(self) -> list[io.BytesIO()]:
        
        full_plot_data = io.BytesIO()
        wobble_plot_data = io.BytesIO()

        self.save_analyzed_subimage(full_plot_data, subimage="full", dpi = 180)
        self.save_analyzed_subimage(wobble_plot_data, dpi = 180)

        return [full_plot_data, wobble_plot_data]

class QStarshotWorker(QObject):

    analysis_progress = Signal(str)
    analysis_results_ready =  Signal(dict)
    analysis_failed = Signal(str)
    thread_finished = Signal()

    def __init__(self, filepath: str | list[str],
                 radius: float = 0.85,
                 min_peak_height: float = 0.25,
                 tolerance: float = 1.0,
                 fwhm: bool = True,
                 recursive: bool = True,
                 invert: bool = False,
                 update_signal: Signal = None,):
        super().__init__()
        
        self._filepath = filepath
        self._radius = radius
        self._min_peak_height = min_peak_height
        self._tolerance = tolerance
        self._fwhm = fwhm
        self._recursive = recursive
        self._invert = invert
        self._update_signal = update_signal

        if type(self._filepath) == str:
            self.starshot = QStarshot(self._filepath)
        else:
            self.starshot = QStarshot.from_multiple_images(self._filepath, kwargs=None)

    def analyze(self):
        try:
            self.starshot.analyze(radius = self._radius,
                              min_peak_height = self._min_peak_height,
                              tolerance = self._tolerance,
                              fwhm = self._fwhm,
                              recursive = self._recursive,
                              invert = self._invert)

            summary_text = [["Minimum circle (wobble) diameter:", 
                         f"{self.starshot.wobble.radius_mm * 2.0 : 2.3f} mm"],
                        ["Position of the wobble circle:",
                         f"{self.starshot.wobble.center.x : 2.1f}, {self.starshot.wobble.center.y : 2.1f}"]]
        
            results = {"summary_text": summary_text,
                   "starshot_obj": self.starshot}
        
            self.analysis_results_ready.emit(results)
            self.thread_finished.emit()
        
        except Exception as err:
            self.analysis_failed.emit(traceback.format_exception_only(err)[-1])
            self.thread_finished.emit()

        
        