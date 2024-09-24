# aind-ophys-dff

This capsule calculates $\Delta F/F$ using the `dff` function from aind-ophys-utils, which executes the following steps:
- Estimate the noise standard deviation $\sigma$ and initial baseline $b$
- Mask active frames, i.e. outliers where $F > b + 3\sigma$
- Obtain $F_0$ by median-filtering the trace using only inactive frames and interpolation
- Calculate $\Delta F/F = (F - F_0) / F_0$ 

## Input

All parameters are passed to dff.py using `python dff.py [parameters]`.
All parameters are defined in __main__ using argparse. The most important one is
'input-dir' which should point to a directory containing an HDF5 file `extraction.h5` with the dataset 'traces/corrected', a 2D array 
of neuropil-corrected traces for each ROI. 

## Output

The main output is the `dff.h5` file. 
It contains 4 datasets: 

`data`: Baseline-corrected fluorescence traces $\Delta F/F$   
`baseline`: Estimated baselines $F_0$    
`noise`:  Estimated standard deviation of the noise in the input traces      
`skewness`:  The skewness of the $\Delta F/F$ traces
