import pandas as pd

from .. import registry
from ..features import TARGET, features_of, make_model


def main(train_path: str, model_path: str, model: str) -> None:
    df_train = pd.read_csv(train_path)
    fitted = make_model(model).fit(df_train, df_train[TARGET])
    registry.save_model(fitted, model_path)

    print(f"{model} on {features_of(fitted)} -> {model_path}")
