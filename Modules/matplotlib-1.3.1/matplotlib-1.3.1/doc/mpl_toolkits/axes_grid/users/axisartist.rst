.. _axisartist-manual:

====================
AXISARTIST namespace
====================

The AxisArtist namespace includes a derived Axes implementation. The
biggest difference is that the artists responsible to draw axis line,
ticks, ticklabel and axis labels are separated out from the mpl's Axis
class, which are much more than artists in the original mpl. This
change was strongly motivated to support curvilinear grid. Here are a
few things that mpl_tootlkits.axisartist.Axes is different from original
Axes from mpl.

* Axis elements (axis line(spine), ticks, ticklabel and axis labels)
  are drawn by a AxisArtist instance. Unlike Axis, left, right, top
  and bottom axis are drawn by separate artists. And each of them may
  have different tick location and different tick labels.

* gridlines are drawn by a Gridlines instance. The change was
  motivated that in curvilinear coordinate, a gridline may not cross
  axis-lines (i.e., no associated ticks). In the original Axes class,
  gridlines are tied to ticks.

* ticklines can be rotated if necessary (i.e, along the gridlines)

In summary, all these changes was to support

* a curvilinear grid.
* a floating axis

.. plot:: mpl_toolkits/axes_grid/examples/demo_floating_axis.py


*mpl_toolkits.axisartist.Axes* class defines a *axis* attribute, which
is a dictionary of AxisArtist instances. By default, the dictionary
has 4 AxisArtist instances, responsible for drawing of left, right,
bottom and top axis.

xaxis and yaxis attributes are still available, however they are set
to not visible. As separate artists are used for rendering axis, some
axis-related method in mpl may have no effect.
In addition to AxisArtist instances, the mpl_toolkits.axisartist.Axes will
have *gridlines* attribute (Gridlines), which obviously draws grid
lines.

In both AxisArtist and Gridlines, the calculation of tick and grid
location is delegated to an instance of GridHelper class.
mpl_toolkits.axisartist.Axes class uses GridHelperRectlinear as a grid
helper. The GridHelperRectlinear class is a wrapper around the *xaxis*
and *yaxis* of mpl's original Axes, and it was meant to work as the
way how mpl's original axes works. For example, tick location changes
using set_ticks method and etc. should work as expected. But change in
artist properties (e.g., color) will not work in general, although
some effort has been made so that some often-change attributes (color,
etc.) are respected.


AxisArtist
==========

AxisArtist can be considered as a container artist with following
attributes which will draw ticks, labels, etc.

 * line
 * major_ticks, major_ticklabels
 * minor_ticks, minor_ticklabels
 * offsetText
 * label


line
----

Derived from Line2d class. Responsible for drawing a spinal(?) line.

major_ticks, minor_ticks
------------------------

Derived from Line2d class. Note that ticks are markers.


major_ticklabels, minor_ticklabels
----------------------------------

Derived from Text. Note that it is not a list of Text artist, but a
single artist (similar to a collection).

axislabel
---------

Derived from Text.


Default AxisArtists
-------------------

By default, following for axis artists are defined.::

  ax.axis["left"], ax.axis["bottom"], ax.axis["right"], ax.axis["top"]

The ticklabels and axislabel of the top and the right axis are set to
not visible.

For example, if you want to change the color attributes of
major_ticklabels of the bottom x-axis ::

  ax.axis["bottom"].major_ticklabels.set_color("b")

Similarly, to make ticklabels invisible ::

  ax.axis["bottom"].major_ticklabels.set_visible(False)

AxisAritst provides a helper method to control the visibility of ticks,
ticklabels, and label. To make ticklabel invisible, ::

  ax.axis["bottom"].toggle(ticklabels=False)

To make all of ticks, ticklabels, and (axis) label invisible ::
    
      ax.axis["bottom"].toggle(all=False)
    
To turn all off but ticks on ::
    
      ax.axis["bottom"].toggle(all=False, ticks=True)
    
To turn all on but (axis) label off ::
    
      ax.axis["bottom"].toggle(all=True, label=False))


ax.axis's __getitem__ method can take multiple axis names. For
example, to turn ticklabels of "top" and "right" axis on, ::

      ax.axis["top","right"].toggle(ticklabels=True))

Note that 'ax.axis["top","right"]' returns a simple proxy object that translate above code to something like below. ::

      for n in ["top","right"]:
        ax.axis[n].toggle(ticklabels=True))

So, any return values in the for loop are ignored. And you should not
use it anything more than a simple method. 

Like the list indexing ":" means all items, i.e., ::

      ax.axis[:].major_ticks.set_color("r")

changes tick color in all axis.


HowTo
=====

1. Changing tick locations and label.

  Same as the original mpl's axes.::

   ax.set_xticks([1,2,3])

2. Changing axis properties like color, etc.

  Change the properties of appropriate artists. For example, to change
  the color of the ticklabels::

    ax.axis["left"].major_ticklabels.set_color("r")

3. To change the attributes of multiple axis::

    ax.axis["left","bottom"].major_ticklabels.set_color("r")

   or to change the attributes of all axis::

    ax.axis[:].major_ticklabels.set_color("r")

4. To change the tick size (length), you need to use
    axis.major_ticks.set_ticksize method. To change the direction of
    the ticks (ticks are in opposite direction of ticklabels by
    default), use axis.major_ticks.set_tick_out method.

    To change the pad between ticks and ticklabels, use
    axis.major_ticklabels.set_pad method.

    To change the pad between ticklabels and axis label,
    axis.label.set_pad method.


Rotation and Alignment of TickLabels
====================================

This is also quite different from the original mpl and can be
confusing. When you want to rotate the ticklabels, first consider
using "set_axis_direction" method. ::

  ax1.axis["left"].major_ticklabels.set_axis_direction("top")
  ax1.axis["right"].label.set_axis_direction("left")

.. plot:: mpl_toolkits/axes_grid/figures/simple_axis_direction01.py

The parameter for set_axis_direction is one of ["left", "right",
"bottom", "top"].

You must understand some underlying concept of directions.

 1. There is a reference direction which is defined as the direction
    of the axis line with increasing coordinate.  For example, the
    reference direction of the left x-axis is from bottom to top.

   .. plot:: mpl_toolkits/axes_grid/figures/axis_direction_demo_step01.py

   The direction, text angle, and alignments of the ticks, ticklabels and
   axis-label is determined with respect to the reference direction

 2. *ticklabel_direction* is either the right-hand side (+) of the
    reference direction or the left-hand side (-).

   .. plot:: mpl_toolkits/axes_grid/figures/axis_direction_demo_step02.py

 3. same for the *label_direction*

   .. plot:: mpl_toolkits/axes_grid/figures/axis_direction_demo_step03.py

 4. ticks are by default drawn toward the opposite direction of the ticklabels.

 5. text rotation of ticklabels and label is determined in reference
    to the *ticklabel_direction* or *label_direction*,
    respectively. The rotation of ticklabels and label is anchored.

   .. plot:: mpl_toolkits/axes_grid/figures/axis_direction_demo_step04.py


On the other hand, there is a concept of "axis_direction". This is a
default setting of above properties for each, "bottom", "left", "top",
and "right" axis. 

 ========== =========== ========= ========== ========= ==========
    ?           ?        left      bottom      right      top
 ---------- ----------- --------- ---------- --------- ----------
 axislabel   direction      '-'       '+'        '+'      '-'
 axislabel   rotation      180         0          0       180
 axislabel   va           center    top       center     bottom
 axislabel   ha           right    center      right     center
 ticklabel   direction      '-'       '+'        '+'      '-'
 ticklabels  rotation       90         0        -90       180
 ticklabel   ha           right    center      right     center
 ticklabel   va           center   baseline    center   baseline
 ========== =========== ========= ========== ========= ==========
  

And, 'set_axis_direction("top")' means to adjust the text rotation
etc, for settings suitable for "top" axis. The concept of axis
direction can be more clear with curved axis.

.. plot:: mpl_toolkits/axes_grid/figures/demo_axis_direction.py

The axis_direction can be adjusted in the AxisArtist level, or in the
level of its child arists, i.e., ticks, ticklabels, and axis-label. ::

  ax1.axis["left"].set_axis_direction("top")

changes axis_direction of all the associated artist with the "left"
axis, while ::

  ax1.axis["left"].major_ticklabels.set_axis_direction("top")

changes the axis_direction of only the major_ticklabels.  Note that
set_axis_direction in the AxisArtist level changes the
ticklabel_direction and label_direction, while changing the
axis_direction of ticks, ticklabels, and axis-label does not affect
them.


If you want to make ticks outward and ticklabels inside the axes, 
use invert_ticklabel_direction method. ::

   ax.axis[:].invert_ticklabel_direction()
 
A related method is "set_tick_out". It makes ticks outward (as a
matter of fact, it makes ticks toward the opposite direction of the
default direction). ::

   ax.axis[:].major_ticks.set_tick_out(True)

.. plot:: mpl_toolkits/axes_grid/figures/simple_axis_direction03.py


So, in summary, 

 * AxisArtist's methods
    * set_axis_direction : "left", "right", "bottom", or "top"
    * set_ticklabel_direction : "+" or "-"
    * set_axislabel_direction : "+" or "-"
    * invert_ticklabel_direction
 * Ticks' methods (major_ticks and minor_ticks)
    * set_tick_out : True or False
    * set_ticksize : size in points
 * TickLabels' methods (major_ticklabels and minor_ticklabels)
    * set_axis_direction : "left", "right", "bottom", or "top"
    * set_rotation : angle with respect to the reference direction
    * set_ha and set_va : see below
 * AxisLabels' methods (label)
    * set_axis_direction : "left", "right", "bottom", or "top"
    * set_rotation : angle with respect to the reference direction
    * set_ha and set_va



Adjusting ticklabels alignment
------------------------------

Alignment of TickLabels are treated specially. See below

.. plot:: mpl_toolkits/axes_grid/figures/demo_ticklabel_alignment.py

Adjusting  pad
--------------

To change the pad between ticks and ticklabels ::

  ax.axis["left"].major_ticklabels.set_pad(10)

Or ticklabels and axis-label ::

  ax.axis["left"].label.set_pad(10)


.. plot:: mpl_toolkits/axes_grid/figures/simple_axis_pad.py


GridHelper
==========

To actually define a curvilinear coordinate, you have to use your own
grid helper. A generalised version of grid helper class is supplied
and this class should suffice in most of cases. A user may provide
two functions which defines a transformation (and its inverse pair)
from the curved coordinate to (rectilinear) image coordinate. Note that
while ticks and grids are drawn for curved coordinate, the data
transform of the axes itself (ax.transData) is still rectilinear
(image) coordinate. ::


    from  mpl_toolkits.axisartist.grid_helper_curvelinear \
         import GridHelperCurveLinear
    from mpl_toolkits.axisartist import Subplot

    # from curved coordinate to rectlinear coordinate.
    def tr(x, y):
        x, y = np.asarray(x), np.asarray(y)
        return x, y-x

    # from rectlinear coordinate to curved coordinate.
    def inv_tr(x,y):
        x, y = np.asarray(x), np.asarray(y)
        return x, y+x


    grid_helper = GridHelperCurveLinear((tr, inv_tr))

    ax1 = Subplot(fig, 1, 1, 1, grid_helper=grid_helper)

    fig.add_subplot(ax1)


You may use matplotlib's Transform instance instead (but a
inverse transformation must be defined). Often, coordinate range in a
curved coordinate system may have a limited range, or may have
cycles. In those cases, a more customized version of grid helper is
required. ::


    import  mpl_toolkits.axisartist.angle_helper as angle_helper

    # PolarAxes.PolarTransform takes radian. However, we want our coordinate
    # system in degree
    tr = Affine2D().scale(np.pi/180., 1.) + PolarAxes.PolarTransform()


    # extreme finder :  find a range of coordinate.
    # 20, 20 : number of sampling points along x, y direction
    # The first coordinate (longitude, but theta in polar)
    #   has a cycle of 360 degree.
    # The second coordinate (latitude, but radius in polar)  has a minimum of 0
    extreme_finder = angle_helper.ExtremeFinderCycle(20, 20,
                                                     lon_cycle = 360,
                                                     lat_cycle = None,
                                                     lon_minmax = None,
                                                     lat_minmax = (0, np.inf),
                                                     )

    # Find a grid values appropriate for the coordinate (degree,
    # minute, second). The argument is a approximate number of grids.
    grid_locator1 = angle_helper.LocatorDMS(12)

    # And also uses an appropriate formatter.  Note that,the
    # acceptable Locator and Formatter class is a bit different than
    # that of mpl's, and you cannot directly use mpl's Locator and
    # Formatter here (but may be possible in the future).
    tick_formatter1 = angle_helper.FormatterDMS()

    grid_helper = GridHelperCurveLinear(tr,
                                        extreme_finder=extreme_finder,
                                        grid_locator1=grid_locator1,
                                        tick_formatter1=tick_formatter1
                                        )


Again, the *transData* of the axes is still a rectilinear coordinate
(image coordinate). You may manually do conversion between two
coordinates, or you may use Parasite Axes for convenience.::

    ax1 = SubplotHost(fig, 1, 2, 2, grid_helper=grid_helper)

    # A parasite axes with given transform
    ax2 = ParasiteAxesAuxTrans(ax1, tr, "equal")
    # note that ax2.transData == tr + ax1.transData
    # Anthing you draw in ax2 will match the ticks and grids of ax1.
    ax1.parasites.append(ax2)


.. plot:: mpl_toolkits/axes_grid/examples/demo_curvelinear_grid.py



FloatingAxis
============

A floating axis is an axis one of whose data coordinate is fixed, i.e,
its location is not fixed in Axes coordinate but changes as axes data
limits changes. A floating axis can be created using
*new_floating_axis* method. However, it is your responsibility that
the resulting AxisArtist is properly added to the axes. A recommended
way is to add it as an item of Axes's axis attribute.::

    # floating axis whose first (index starts from 0) coordinate
    # (theta) is fixed at 60

    ax1.axis["lat"] = axis = ax1.new_floating_axis(0, 60)
    axis.label.set_text(r"$\theta = 60^{\circ}$")
    axis.label.set_visible(True)


See the first example of this page.

Current Limitations and TODO's
==============================

The code need more refinement. Here is a incomplete list of issues and TODO's

* No easy way to support a user customized tick location (for
  curvilinear grid). A new Locator class needs to be created.

* FloatingAxis may have coordinate limits, e.g., a floating axis of x
  = 0, but y only spans from 0 to 1.

* The location of axislabel of FloatingAxis needs to be optionally
  given as a coordinate value. ex, a floating axis of x=0 with label at y=1
