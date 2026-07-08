I want to create a toy MC to simulate a cosmic ray stand.

# detectors
I want to define 3D rectangular volumes (dx,dy,dz). I will use their center and then extend by dx/2, dy/2 and dz/2 their dimension in space.

I can add any number of rectangular volumes in this stand. I do not care for overlapping volumes.

Each detector has custom efficiency (from 0 to 1).

I assume that the "detector response" is instantaneous and binary: the detector sees the particle or not.

# tracks
I want to create random track, simulating cosmic rays. I do not care about energy and possible interaction. This toyMC is only geometrical. That's why I'm not using GEANT4.

The interpecta with the xy plan z=0 will be uniform distributed. Then phi uniform generated. Then theta as the cosmic ray distribution (a simple way is cos^2 theta but feel free to suggest more truthfull ways)

# variables
In order to simulate my sistem I want to:
- estimate the cosmic rays rate on a single detector
- estimate the cosmic rays rate of a logic expression of detectors ( T1 and T2 and T3 and not-T4)
- estimate the cosmic rays rate on a detector of a logic expresison of detectors (rate on D1 of track passing "T1 and T2")