# Sample CGM trace

`sample_cgm.csv` is a 48-hour excerpt (192 readings, 15-minute interval) from recording `1002_1_20210521` of ShanghaiT1DM. The file stores only offsets from the end of the trace in minutes, not dates. The app shifts the trace so its last reading falls at the moment you load it, so you can try the app without a sensor. Over these 48 hours, glucose goes below 70 mg/dL 13 times and above 180 mg/dL 46 times, so the sample produces both hypo and hyper forecasts.

Source: Zhao Q., Zhu J., Shen X. et al., "Chinese diabetes datasets for data-driven machine learning", *Scientific Data* 10, 35 (2023). Dataset: Zhu, Jinhao (2022), Diabetes Datasets-ShanghaiT1DM and ShanghaiT2DM, figshare, https://doi.org/10.6084/m9.figshare.20444397. Licensed CC BY 4.0. The values are unchanged; the timestamps have been replaced by relative offsets.
