import os
import conda
import matplotlib.animation as animation


##################################################
#Hack to fix missing PROJ4 env var

conda_file_dir = conda.__file__
conda_dir = conda_file_dir.split('lib')[0]
proj_lib = os.path.join(os.path.join(conda_dir, 'Library'), 'share')
os.environ["PROJ_LIB"] = proj_lib
##################################################


coord_list = [-34.6037, -58.3816, -34.5754, -58.436, -34.6021, -58.3845, 39.0438, -77.4874, 39.0438, -77.4874]
coord_iter = iter(coord_list)

import matplotlib.pyplot as plt
from mpl_toolkits.basemap import Basemap

def init():
    point.set_data([],[])
    return point,

def animate(i):
    #print('mapping..')
    #update lons and lats
    next_frame = get_next_coord()
    print('mapping next_frame is : ' + str(next_frame))
    #print('lats is: ' + str(lats) + '   '+'lons is : ' + str(lons))
    x,y = m(next_frame[1],next_frame[0])
    point.set_data(x,y)
    return point,

def get_next_coord(coords=coord_iter):
    nextx=next(coords)
    nexty=next(coords)
    return nextx,nexty
    
def f():
    global anim
    anim = animation.FuncAnimation(plt.gcf(),animate,init_func=init,frames=20,repeat=True,interval=1000,blit=True)


#Config Map
m = Basemap(lat_0=0, lon_0=-40, projection='robin',resolution='c')
#m.drawmapboundary(fill_color='lightblue')
#m.fillcontinents(color='tan',lake_color='lightblue')
#m.drawparallels()
m.drawcoastlines(color='grey', linewidth=1.0)
m.shadedrelief()

#Init and define first point

x,y = m(0,0)
point = m.plot(x,y,'ro',markersize=5)[0]

#Call Animator

f()
plt.show()
