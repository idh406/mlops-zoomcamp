from calendar import month
import pandas as pd

from sklearn.feature_extraction import DictVectorizer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error

from datetime import date, timedelta, datetime
from dateutil.relativedelta import relativedelta

import pickle

from prefect import flow, task, get_run_logger
from prefect.task_runners import SequentialTaskRunner

from prefect.deployments import DeploymentSpec
from prefect.orion.schemas.schedules import CronSchedule
from prefect.flow_runners import SubprocessFlowRunner


@task
def get_paths(dt):
    #date_object = datetime.strptime(date_string, "%d %B, %Y")
    if dt == None:
        dt = date.today()
    if isinstance(dt, str):
        dt = datetime.strptime(dt, "%Y-%m-%d")
    
    train_set_date = dt - relativedelta(months=2)
    val_set_date = dt - relativedelta(months=1)
    train_set_month = "%02d" % (train_set_date.month)
    val_set_month = "%02d" % (val_set_date.month)
    train_path = f'./data/fhv_tripdata_{train_set_date.year}-{train_set_month}.parquet'
    val_path = f'./data/fhv_tripdata_{val_set_date.year}-{val_set_month}.parquet'
    
    return train_path, val_path


@task
def read_data(path):
    df = pd.read_parquet(path)
    return df

@task
def prepare_features(df, categorical, train=True):
    logger = get_run_logger()
    
    df['duration'] = df.dropOff_datetime - df.pickup_datetime
    df['duration'] = df.duration.dt.total_seconds() / 60
    df = df[(df.duration >= 1) & (df.duration <= 60)].copy()

    mean_duration = df.duration.mean()
    if train:
        logger.info(f"The mean duration of training is {mean_duration}")
    else:
        logger.info(f"The mean duration of validation is {mean_duration}")
    
    df[categorical] = df[categorical].fillna(-1).astype('int').astype('str')
    return df

@task
def train_model(df, categorical):

    logger = get_run_logger()

    train_dicts = df[categorical].to_dict(orient='records')
    dv = DictVectorizer()
    X_train = dv.fit_transform(train_dicts) 
    y_train = df.duration.values

    logger.info(f"The shape of X_train is {X_train.shape}")
    logger.info(f"The DictVectorizer has {len(dv.feature_names_)} features")

    lr = LinearRegression()
    lr.fit(X_train, y_train)
    y_pred = lr.predict(X_train)
    mse = mean_squared_error(y_train, y_pred, squared=False)
    logger.info(f"The MSE of training is: {mse}")
    return lr, dv

@task
def run_model(df, categorical, dv, lr):
    
    logger = get_run_logger()

    val_dicts = df[categorical].to_dict(orient='records')
    X_val = dv.transform(val_dicts) 
    y_pred = lr.predict(X_val)
    y_val = df.duration.values

    mse = mean_squared_error(y_val, y_pred, squared=False)
    logger.info(f"The MSE of validation is: {mse}")
    return

@flow(task_runner=SequentialTaskRunner())
def main(date=None):

    train_path, val_path = get_paths(date).result()

    categorical = ['PUlocationID', 'DOlocationID']

    df_train = read_data(train_path)
    df_train_processed = prepare_features(df_train, categorical)

    df_val = read_data(val_path)
    df_val_processed = prepare_features(df_val, categorical, False)

    # train the model
    lr, dv = train_model(df_train_processed, categorical).result()
    run_model(df_val_processed, categorical, dv, lr)
    

    with open('./models/model-'+ date + '.bin', 'wb') as f_out:
        pickle.dump(lr, f_out)
    with open('./artifacts/dv-'+ date + '.b', 'wb') as f_out:
        pickle.dump(dv, f_out)


main(date="2021-08-15")

# DeploymentSpec(
#     name="cron-schedule-deployment",
#     flow_location=".",
#     schedule=CronSchedule(
#         cron="0 9 15 * *",
#         timezone="America/Chicago"),
# )


# from prefect.deployments import DeploymentSpec
# from prefect.orion.schemas.schedules import IntervalSchedule
# from prefect.flow_runners import SubprocessFlowRunner

# DeploymentSpec(
#     flow=main,
#     name="model_training_2",
#     schedule=CronSchedule(
#         cron="0 9 15 * *",
#         timezone="America/Chicago"),
#     flow_runner=SubprocessFlowRunner(),
#     tags=["ml"]
# )


