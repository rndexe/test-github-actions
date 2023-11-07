import requests
import json
import os
import re
import zipfile
import geopandas as gpd
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

from shapely.geometry import Point

# Shape files from  https://onlinemaps.surveyofindia.gov.in/Digital_Product_Show.aspx
# Restrict to punjab only for optimization

districts_file_name = "PUNJAB_DISTRICT_BDY.json"
districts_gdf = gpd.read_file(districts_file_name)

DATE = datetime.now(tz=ZoneInfo("Asia/Kolkata")).strftime('%Y-%m-%d')
SENSORS = ["modis","vf375"]
API_VERSION = "v2"
STATE = "PB"

print(f"Getting data for {DATE}")

s = requests.Session()
fires_gdf_array = []

for SENSOR in SENSORS:

    print(f'Connecting to {SENSOR} API...')
    
    r = s.get(f"https://bhuvan-app1.nrsc.gov.in/2dresources/fire_shape/create_shapefile_v2.php?date={DATE}&s={SENSOR}&y1=2023",timeout=(10,15))    
    url = re.search(r'(?<=src=").*?(?=[\*"])',r.text)
    filename = re.search(r'[^\/]+(?=\.[^\/.]*$)',url[0])
    zipfile_name = f"shapefile_{SENSOR}.zip"

    print(f'Downloading {SENSOR} shapefile...')
    
    rshp = s.get(url[0],timeout=(10,15))
    with open(zipfile_name, 'wb') as fd:
        for chunk in rshp.iter_content(chunk_size=128):
            fd.write(chunk)

    print("Done")

    _gdf = gpd.read_file("zip:///"+os.path.realpath(zipfile_name)+"!shape/"+filename[0]+".shp")
    _gdf = _gdf[(_gdf.state.str.contains('PB')) & (_gdf.cropmask.notna())]
    #_gdf.to_csv(f'fires_temp_{SENSOR}.csv', index=False)
    if (SENSOR == "modis"):
        _gdf = _gdf[_gdf.detection_ > 30]
    else:
        _gdf = _gdf[_gdf.detection_ > 7]

    fires_gdf_array.append(_gdf)

#
fires_gdf = pd.concat([fires_gdf_array[0],fires_gdf_array[1]])
fires_gdf['district'] = None
geometry = [Point(xy) for xy in zip(fires_gdf['lon'], fires_gdf['lat'])]

print("Identifying districts")

fires_gdf['geometry'] = geometry
for i, fire in fires_gdf.iterrows():
    for j, district in districts_gdf.iterrows():
        if fire['geometry'].within(district['geometry']):
            fires_gdf.at[i, 'district'] = district['District']
#

fires_gdf.drop(inplace=True,columns=['brightness','cropmask','geometry','scanpixel_','trackpixel','mailsent','mailsent_t','village_na','id','orbitno','coverage_f'])
fires_gdf = fires_gdf[fires_gdf.district.notna()]

print(fires_gdf)
print("Writing to json")

todays_data = {}
todays_data["last_update"] = datetime.now(tz=ZoneInfo("Asia/Kolkata")).strftime('%-I:%M %p, %d %b %Y')

value_counts = fires_gdf['district'].value_counts().to_dict()
# Select the column values from df1
column_values = districts_gdf['District'].unique()
result_json = {}
for value in column_values:
    result_json[str(value)] = value_counts.get(value, 0)

todays_data[STATE] = json.loads(fires_gdf.to_json(orient="records"))
todays_data["districts"] = result_json
with open(f'docs/{API_VERSION}/{DATE}.json', 'w') as outfile:
    json.dump(todays_data, outfile)
