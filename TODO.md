# TODO list

+ Add integration with the Databricks platform (by copying static files to appropiate locations and referring them in the HTML rendered by Jinja2)
+ ~~Let the user choose correlation threshold for variable rejection~~
+ Create test suite
+ ~~Check support for other pandas / Spark versions~~
+ Add support for complex Spark SQL data types (`ArrayType`, `StructType` and `MapType`)
+ Add verbosity option/progress bar (since profiling in large tables can be eternal)
+ Add support for infinite values
+ Generate `.describe()`-like dataframe for non-browser users
+ (Long term): drop pandas dependency
