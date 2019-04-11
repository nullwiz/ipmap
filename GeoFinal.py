# -*- coding: utf-8 -*-
"""
Created on Mon Apr  8 18:44:14 2019

@author: nullwiz & leculet
"""
import urllib.request
import json
import codecs
import os
import conda
import fileinput
import ipaddress
import matplotlib.animation as animation
import subprocess 

##################################################
#Hack to fix missing PROJ4 env var

conda_file_dir = conda.__file__
conda_dir = conda_file_dir.split('lib')[0]
proj_lib = os.path.join(os.path.join(conda_dir, 'share'), 'proj')
os.environ["PROJ_LIB"] = proj_lib


import matplotlib.pyplot as plt
from mpl_toolkits.basemap import Basemap

#Emulate tracert stin 
def CallTraceRoute():
    traceroute = 'traceroute'
    ip_list=[]
    subprocess.call(['traceroute','google.com'],shell=true,stdout=subprocess.PIPE)
    stdout = process.communicate()[0]
    while True:
        output = process.stdout.readline()
        for line in output:
            line = line.translate(str.maketrans('','','()'))
            if output == '' and process.poll() is not None:
                break
            if output:
                try:
                    piaddress.ip_address
    rc = process.poll()
    
    
    
    
    
    for line in fileinput.input():
        #Si hay ips entre (), saquemoslas antes de verificar si son validas
        line = line.translate(str.maketrans('','','()'))
        sLine = line.split( )
        for i in sLine:
            try:
                ipaddress.ip_address(i)
                # legal
                if i not in ip_list:
                    ip_list.append(i)
            except ValueError:
                pass
    #dont parse first local hop
    return ip_list[1:]



###################################################
def ParseTraceRoute():
    ip_list=[]
    for line in fileinput.input():
        #Si hay ips entre (), saquemoslas antes de verificar si son validas
        line = line.translate(str.maketrans('','','()'))
        sLine = line.split( )
        for i in sLine:
            try:
                ipaddress.ip_address(i)
                # legal
                if i not in ip_list:
                    ip_list.append(i)
            except ValueError:
                pass
    #dont parse first local hop
    return ip_list[1:]


def init():
    point.set_data([],[])
    return point,

def animate(i):
    print('mapping..')
    #update lons and lats
    lats = next(coord_iter)
    lons = next(coord_iter)
    print('lats is: ' + str(lats) + '   '+'lons is : ' + str(lons))
    x,y = m(lons,lats)
    point.set_data(x,y)
    return point,

#Config Map
m = Basemap(lat_0=0, lon_0=0, projection='moll',resolution='l')
m.drawmapboundary(fill_color='lightblue')
m.fillcontinents(color='tan',lake_color='lightblue')
#m.drawcoastlines()
m.shadedrelief()
#Init and define first point
x,y = m(0,0)
point = m.plot(x,y,'ro',markersize=5)[0]

ip_list = []
ip_list=ParseTraceRoute()
json_list = []
coord_list = []

#Read from STDIN
[print('About to get coordinates for: ' + ip_list[i]) for i in range(0,len(ip_list))]

for i in ip_list:
                                                                    ##Change for + data
    with urllib.request.urlopen('http://ip-api.com/json/'+str(i)+ '?fields=country,city,lat,lon') as f:
            json_list.append(json.loads(f.read()))


#Append for our fav json
for i in range(0,len(json_list)):
    coord_list.append(float(json_list[i]['lat']))

    coord_list.append(float(json_list[i]['lon']))

#Print coordinates for debugging
print('Requests for latitude and longitude to all of the ips responded with:'  +str(coord_list))

#Lo mas crucial es hacer este iterador para que la variable que updatea el frame (animate) pueda leerlo de main y ir loopeando

coord_iter = iter(coord_list)
#Call Animator
anim = animation.FuncAnimation(plt.gcf(),animate,init_func=init,frames=20,repeat=True,interval=1000,blit=True)

plt.show()

