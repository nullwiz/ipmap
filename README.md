## ipmap
This python program reads traceroute from stdin (or tracert on windows) and maps it to a point in the Basemap matplotlib instance and animates it using the FuncAnimator.  
## installation

## usage
<code>traceroute -I google.com | python ipmap.py</code>
### possible fixes
  [1] plot a great circle instead of points (we may have to re-implement the parser and input 4 zipped lat/lons*)
      --> m.drawgreatcircle(startlon,startlat,arrlon,arrlat, linewidth=2, color='orange')
      or just use plot()
          plt.plot([-0.08, 132], [51.53, 43.17], color='red',  transform=ccrs.Geodetic())
       *but we dont know how we can animate that^ 
              try this https://stackoverflow.com/questions/52082435/plotting-animation-on-basemap
      
       

  [2] fix PROJ_LIB (proj4 enviroment issue-- the fix is to set the PATH in .bashrc, maybe?)
