import glob
import os
import shutil
import random
import time
import json
from pyspark.sql import SparkSession
from utils import createImageDataSet, streaming_schema

## To download the CIFAR10 dataset, run below two commands
# !wget -c https://www.cs.toronto.edu/~kriz/cifar-10-python.tar.gz
# !tar -xvzf cifar-10-python.tar.gz
# Update the below path after downloading the files
dataset_path = os.getcwd() + '/cifar-10-batches-py/'

output_path = 'streams/input/'
output_archive = 'streams/archive'
tracker_path = 'logs/tracker.json'
col_labels = ["batch_id", "batch_size", "triggered", "start", "end", "accuracy", "env"]


def clear_pushes():
    """
    Clear the old files (if present) before pushing new images
    :return:
    """
    files = glob.glob(output_path+"*")
    for f in files:
        os.chmod(f, 0o777)
        os.remove(f)

    if os.path.exists(tracker_path):
        os.remove(tracker_path)

    for root, dirs, files in os.walk(output_archive, topdown=False):
        for dir in dirs:
            shutil.rmtree(os.path.join(root,dir), ignore_errors=True)


def log(batch_id, batch_size):
    """
    Creates a spark cluster to log the details of the images being pushed.
    :param batch_id:
    :param batch_size:
    :return:
    """
    spark = SparkSession.builder. \
        appName("ImageDataPush"). \
        master("local[*]"). \
        config("spark.ui.port", "4051"). \
        config("spark.executor.memory", "16G"). \
        config("spark.driver.memory", "16G"). \
        getOrCreate()

    new_df = spark.createDataFrame([(batch_id, batch_size, time.time(), 0.0, 0.0, 0.0, "mac_cpu")], col_labels, streaming_schema)
    if not os.path.exists(tracker_path):
        new_df.toPandas().to_json(tracker_path, orient='records', force_ascii=False, lines=True)
    else:
        df = spark.read.json(tracker_path)
        df = df.unionByName(new_df)
        df.toPandas().to_json(tracker_path, orient='records', force_ascii=False, lines=True)

    spark.stop()


def send_images(batch_id, images_to_push):
    """
    Save the images to the streaming directory used by the other spark cluster.
    :param batch_id:
    :param images_to_push:
    :return:
    """
    json_dict = []
    for data, label in images_to_push:
        json_dict.append({"idx": batch_id, "data": data.tolist(), "label": label})
    with open(output_path + f"batch_{batch_id}.json", "x") as outfile:
        json.dump(json_dict, outfile)


def push(type, interval, stop):
    """
    Triggers images based on the parameters given to the streaming directory
    :param type: constant, random, increasing
    :param interval: Speed of pushing the images
    :param stop: Number of image triggers
    :return:
    """
    train_dataset, test_dataset, _ = createImageDataSet(dataset_path)

    complete_dataset = train_dataset
    complete_dataset.extend(test_dataset)

    size = len(complete_dataset)
    num_batch = 0
    batch_id = 1
    while stop > 0:
        if batch_id > 1:
            time.sleep(interval)

        if type[0] == "constant":
            num_batch = type[1]
        elif type[0] == "random":
            num_batch = random.randint(type[1][0], type[1][1])
        else:
            num_batch += type[1]

        images_to_push = []
        log(batch_id, num_batch)
        for _ in range(num_batch):
            random_index = random.randint(1, size)
            images_to_push.append(complete_dataset[random_index])

        send_images(batch_id, images_to_push)
        print(f"Pushed {batch_id} data")
        batch_id += 1
        stop -= 1


if __name__ == '__main__':

    push_types = [
        ("constant", 50),
        ("random", (50, 200)),
        ("increasing", 5)
    ]

    interval = 5
    stop = 16
    clear_pushes()
    print("Starting pushing...")
    time.sleep(5)

    push(push_types[2], interval, stop)
