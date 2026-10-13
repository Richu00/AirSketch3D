"""Matplotlib 3D viewer, run as a separate process so it never clashes with the OpenCV window on macOS.
Usage: python standalone/view3d.py shape_outline.npy"""
import sys

import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

HEIGHT = 0.6
outline = np.load(sys.argv[1])
n = len(outline)
bottom = [(x, y, 0.0) for x, y in outline]
top = [(x, y, HEIGHT) for x, y in outline]
faces = [bottom, top] + [[bottom[i], bottom[(i + 1) % n], top[(i + 1) % n], top[i]] for i in range(n)]

fig = plt.figure("AirSketch3D - drag to rotate, close window to continue")
ax = fig.add_subplot(111, projection="3d")
ax.add_collection3d(Poly3DCollection(faces, facecolors="#4c9be8", edgecolors="#1b4f8a", linewidths=0.5, alpha=0.85))
ax.set_xlim(-1.2, 1.2); ax.set_ylim(-1.2, 1.2); ax.set_zlim(-0.3, HEIGHT + 0.9)
ax.set_box_aspect((1, 1, 0.6))
plt.show()
