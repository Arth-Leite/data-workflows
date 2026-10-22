from sklearn.preprocessing import FunctionTransformer


def clip_ratio_fn(X):
    return X.clip(0.8, 2.0)


clip_ratio = FunctionTransformer(clip_ratio_fn, feature_names_out="one-to-one")
