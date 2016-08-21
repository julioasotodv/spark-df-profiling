# HTML profiling reports from Apache Spark DataFrames

Generates profile reports from an [Apache Spark DataFrame](https://spark.apache.org/docs/latest/sql-programming-guide.html). It is based on [`pandas_profiling`](https://github.com/JosPolfliet/pandas-profiling), but for Spark's DataFrames instead of pandas'.

For each column the following statistics - if relevant for the column type - are presented in an interactive HTML report:

* **Essentials**:  type, unique values, missing values
* **Quantile statistics** like minimum value, Q1, median, Q3, maximum, range, interquartile range
* **Descriptive statistics** like mean, mode, standard deviation, sum, median absolute deviation, coefficient of variation, kurtosis, skewness
* **Most frequent values**
* **Histogram**

All operations are done *efficiently*, which means that no Python UDFs or `.map()` transformations are used at all; only Spark SQL's Catalyst (and the Tungsten execution engine) is used for the retrieval of all statistics.

## Demo

Available [here](http://nbviewer.jupyter.org/github/julioasotodv/spark-df-profiling/blob/master/examples/Demo.ipynb).


## Installation

If you are using [Anaconda](https://www.continuum.io/downloads), you already have all the needed dependencies. So you just have to `pip install` the package without dependencies (just in case pip tries to overwrite your current dependencies):

	pip install --no-deps spark-df-profiling

If you don't have pandas and/or matplotlib installed:

	pip install spark-df-profiling

## Usage

The profile report is written in HTML5 and CSS3, which means that you may require a modern browser.

Keep in mind that you need a working Spark cluster (or a local Spark installation). The report must be created from `pyspark`. To point pyspark driver to your Python environment, you must set the environment variable `PYSPARK_DRIVER_PYTHON` to your python environment where spark-df-profiling is installed. For example, for Anaconda:

	export PYSPARK_DRIVER_PYTHON=/path/to/your/anaconda/bin/python

And then you can execute `/path/to/your/bin/pyspark` to enter pyspark's CLI.

### Jupyter Notebook (formerly IPython)
We recommend generating reports interactively by using the Jupyter notebook.

To use pyspark with Jupyter, you must also set `PYSPARK_DRIVER_PYTHON`:

	export PYSPARK_DRIVER_PYTHON=/path/to/your/anaconda/bin/python

And then:

	IPYTHON_OPTS="notebook" /path/to/your/bin/pyspark

In `spark 2.0.X` `IPYTHON_OPTS` is removed: the environment variable you want to set is `PYSPARK_DRIVER_PYTHON_OPTS`:

	PYSPARK_DRIVER_PYTHON_OPTS="notebook" /path/to/your/bin/pyspark

Now you can create a new notebook, which will run pyspark.


To use spark-df-profiling, start by loading in your Spark DataFrame, e.g. by using

```python
# sqlContext is probably already created for you.
# To load a parquet file as a Spark Dataframe, you can:
df = sqlContext.read.parquet("/path/to/your/file.parquet")
# And you probably want to cache it, since a lot of 
# operations will be done while the report is being generated:
df_spark = df.cache()
```

To display the report in a Jupyter notebook, run:

```python
import spark_df_profiling
spark_df_profiling.ProfileReport(df_spark)
```

If you want to generate a HTML report file, save the ProfileReport to an object and use the `.to_file()` method:

```python
profile = spark_df_profiling.ProfileReport(df_spark)
profile.to_file(outputfile="/tmp/myoutputfile.html")
```

## Dependencies

* Python (`>=2.7`)
* Apache Spark (who would imagine!) -> requires Spark `>=1.5.0` (compatible with `2.0.0` also).
* **An internet connection.** spark-df-profiling requires an internet connection to download the Bootstrap and JQuery libraries. You can choose to embed them in the HTML template code, should you desire.
* pandas (`>=0.16`) -> needed for internal data arrangement. Only needed in the Spark driver.
* matplotlib (`>=1.4`) -> needed for histogram creation. Only needed in the Spark driver.
