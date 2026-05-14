# Pitch Visualizer
An interactive Streamlit app for exploring any MLB pitcher's arsenal using
Statcast data. Search a pitcher, pick one or more seasons, and generate
visualizations of their pitch movement, velocity distribution, and usage.

## Features

- Pitcher search by full name, last name, or "Last, First"
- Multi-season selection (Statcast era: 2015–present)
- Three chart types: pitch movement, velocity distribution, usage breakdown
- Handedness-aware horizontal break (arm side / glove side adjusted for LHP/RHP)
- Per-pitch summary table with velocity, spin rate, and movement averages
- CSV export of summary data

## Setup
   
```
   pip install -r requirements.txt
   streamlit run pitch_visualizer.py
```

## Data source

MLB Statcast via [pybaseball](https://github.com/jldbc/pybaseball).

## Tools used

- Python 3
- Streamlit
- pybaseball
- pandas
- matplotlib

## Sample Output

(using Nolan McLean's 2025 Season)

- ![SAMPLE: Nolan McLean 2025 Pitch Movement](mclean_pitchmovement_2025.png)
- McLean gets a ridiculous amount of movement on his pitches, namely with his curveball, which drops hard vertically and towards glove side. The most interesting thing in McLean's 2025 pitch chart is the overlap between his cutter and changeup. McLean's ability to utilize both with arm side break is imperative for his ability to induce Ks and generate CSW. 
- ![SAMPLE: Nolan McLean 2025 Pitch Usage](mclean_pitchusage_2025.png)
- McLean is primarily a sinker/sweeper pitcher, which is unsurprising due to the terrific movement profiles of both pitches and their ability to tunnel off of each other. McLean features a 6-pitch arsenal with multiple fastballs, breakers, and off-speed pitches, which has allowed him to attack both LHB and RHB in a variety of ways.
- ![SAMPLE: Nolan McLean 2025 Velocity Distribution](mclean_velodistribution_2025.png)
- To connect back to the pitch movement chart, the overlap between pitch velocities here is something that McLean's pitches excel at. McLean's Sinker, Four-Seam, and Cutter are all thrown at 90+ mph and his changeup and sweeper have significant overlap in terms of velocity. The overlapping movement profiles and velocity profiles of many of McLean's pitches allow for them to look the same coming out of his hand, which makes it hard for batters to identify which of McLean's 6 pitches is being thrown. 

## Future Improvements
- Pitcher vs. pitcher comparison view
- Filter pitches by count, batter handedness, or game situation
- Pitch outcome overlays (whiffs/hard contact) 
