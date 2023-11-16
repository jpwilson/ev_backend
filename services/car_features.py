from typing import Dict, List
from models.pydantic_models import CarRead


def get_car_prices(cars: List[CarRead]) -> Dict[str, List[int]]:
    price_buckets = {
        "under_20k": [],
        "20_30k": [],
        "30_40k": [],
        "40_50k": [],
        "50_60k": [],
        "60_80k": [],
        "80_100k": [],
        "100_130k": [],
        "130_180k": [],
        "180_220k": [],
        "over_220k": [],
    }

    for car in cars:
        if car.current_price is None:
            continue

        if car.current_price < 20000:
            price_buckets["under_20k"].append(car.id)
        elif 20000 <= car.current_price < 30000:
            price_buckets["20_30k"].append(car.id)
        elif 30000 <= car.current_price < 40000:
            price_buckets["30_40k"].append(car.id)
        elif 40000 <= car.current_price < 50000:
            price_buckets["40_50k"].append(car.id)
        elif 50000 <= car.current_price < 60000:
            price_buckets["50_60k"].append(car.id)
        elif 60000 <= car.current_price < 80000:
            price_buckets["60_80k"].append(car.id)
        elif 80000 <= car.current_price < 100000:
            price_buckets["80_100k"].append(car.id)
        elif 100000 <= car.current_price < 130000:
            price_buckets["100_130k"].append(car.id)
        elif 130000 <= car.current_price < 180000:
            price_buckets["130_180k"].append(car.id)
        elif 180000 <= car.current_price < 220000:
            price_buckets["180_220k"].append(car.id)

        # Over 220k
        elif car.current_price > 220000:
            price_buckets["over_220k"].append(car.id)

    return price_buckets


def get_acceleration(cars: List[CarRead]) -> Dict[str, List[int]]:
    acceleration_buckets = {
        "under_2s": [],
        "2_3s": [],
        "3_4s": [],
        "4_5s": [],
        "6_8s": [],
        "8_10s": [],
        "over_10s": [],
    }

    for car in cars:
        if car.acceleration_0_60 is None:
            continue

        if car.acceleration_0_60 < 2:
            acceleration_buckets["under_2s"].append(car.id)
        elif 2 <= car.acceleration_0_60 < 3:
            acceleration_buckets["2_3s"].append(car.id)
        elif 3 <= car.acceleration_0_60 < 4:
            acceleration_buckets["3_4s"].append(car.id)
        elif 4 <= car.acceleration_0_60 < 5:
            acceleration_buckets["4_5s"].append(car.id)
        elif 6 <= car.acceleration_0_60 < 8:
            acceleration_buckets["6_8s"].append(car.id)
        elif 8 <= car.acceleration_0_60 < 10:
            acceleration_buckets["8_10s"].append(car.id)
        elif car.acceleration_0_60 >= 10:
            acceleration_buckets["over_10s"].append(car.id)

    return acceleration_buckets


def get_top_speed(cars: List[CarRead]) -> Dict[str, List[int]]:
    top_speed_buckets = {
        "under_100": [],
        "100_120": [],
        "120_150": [],
        "150_180": [],
        "180_200": [],
        "over_200": [],
    }

    for car in cars:
        if car.top_speed is None:
            continue

        if car.top_speed < 100:
            top_speed_buckets["under_100"].append(car.id)
        elif 100 <= car.top_speed < 120:
            top_speed_buckets["100_120"].append(car.id)
        elif 120 <= car.top_speed < 150:
            top_speed_buckets["120_150"].append(car.id)
        elif 150 <= car.top_speed < 180:
            top_speed_buckets["150_180"].append(car.id)
        elif 180 <= car.top_speed < 200:
            top_speed_buckets["180_200"].append(car.id)
        elif car.top_speed >= 200:
            top_speed_buckets["over_200"].append(car.id)

    return top_speed_buckets


def bucket_cars_by_attributes(cars: List[CarRead]) -> Dict[str, Dict[str, List[int]]]:
    price_buckets = get_car_prices(cars)
    acceleration_buckets = get_acceleration(cars)
    top_speed_buckets = get_top_speed(cars)
    car_features = {
        "prices": price_buckets,
        "acceleration": acceleration_buckets,
        "top_speed": top_speed_buckets,
        # ... Other feature buckets ...
    }
    return car_features
