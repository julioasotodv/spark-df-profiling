import sys

try:
    from StringIO import BytesIO
except ImportError:
    from io import BytesIO

try:
    from urllib import quote
except ImportError:
    from urllib.parse import quote

import base64
from itertools import product

import matplotlib
matplotlib.use('Agg')

import numpy as np
import os
import pandas as pd
import spark_df_profiling.formatters as formatters, spark_df_profiling.templates as templates
from matplotlib import pyplot as plt
from pkg_resources import resource_filename
import six

from pyspark.sql import DataFrame as SparkDataFrame
from pyspark.sql.functions import (abs as df_abs, col, count, countDistinct, 
                                   max as df_max, mean, min as df_min,  
                                   sum as df_sum, when
                                   )

# Backwards compatibility with Spark 1.5:
try:
    from pyspark.sql.functions import variance, stddev, kurtosis, skewness
    spark_version = "1.6+"
except ImportError:
    from pyspark.sql.functions import pow as df_pow, sqrt
    def variance_custom(column, mean, count):
        return df_sum(df_pow(column - mean, int(2))) / float(count-1)
    def skewness_custom(column, mean, count):
        return ((np.sqrt(count) * df_sum(df_pow(column - mean, int(3)))) / df_pow(sqrt(df_sum(df_pow(column - mean, int(2)))),3))
    def kurtosis_custom(column, mean, count):
        return ((count*df_sum(df_pow(column - mean, int(4)))) / df_pow(df_sum(df_pow(column - mean, int(2))),2)) -3
    spark_version = "<1.6"


def describe(df, bins, corr_reject, **kwargs):
    if not isinstance(df, SparkDataFrame):
        raise TypeError("df must be of type pyspark.sql.DataFrame")

    # Number of rows:
    table_stats = {"n": df.count()}
    if table_stats["n"] == 0:
        raise ValueError("df cannot be empty")
    
    try:
        # reset matplotlib style before use
        # Fails in matplotlib 1.4.x so plot might look bad
        matplotlib.style.use("default")
    except:
        pass

    matplotlib.style.use(resource_filename(__name__, "spark_df_profiling.mplstyle"))
    
    # Function to "pretty name" floats:
    def pretty_name(x):
        x *= 100
        if x == int(x):
            return '%.0f%%' % x
        else:
            return '%.1f%%' % x

    # Function to compute the correlation matrix:
    def corr_matrix(df, columns=None):
        if columns is None:
            columns = df.columns
        combinations = list(product(columns,columns))
        
        def separate(l, n):
            for i in range(0, len(l), n):
                yield l[i:i+n]

        grouped = list(separate(combinations,len(columns)))
        df_cleaned = df.select(*columns).na.drop(how="any")
        
        for i in grouped:
            for j in enumerate(i):
                i[j[0]] = i[j[0]] + (df_cleaned.corr(str(j[1][0]), str(j[1][1])),)
                
        df_pandas = pd.DataFrame(grouped).applymap(lambda x: x[2])
        df_pandas.columns = columns
        df_pandas.index = columns
        return df_pandas

    # Compute histogram (is not as easy as it looks):
    def create_hist_data(df, column, minim, maxim, bins=10):

        def create_all_conditions(current_col, column, left_edges, count=1):
            """
            Recursive function that exploits the
            ability to call the Spark SQL Column method
            .when() in a recursive way.
            """
            left_edges = left_edges[:]
            if len(left_edges) == 0:
                return current_col
            if len(left_edges) == 1:
                next_col = current_col.when(col(column) >= float(left_edges[0]), count)
                left_edges.pop(0)
                return create_all_conditions(next_col, column, left_edges[:], count+1)
            next_col = current_col.when((float(left_edges[0]) <= col(column)) 
                                        & (col(column) < float(left_edges[1])), count)
            left_edges.pop(0)
            return create_all_conditions(next_col, column, left_edges[:], count+1)
        
        num_range = maxim - minim
        bin_width = num_range / float(bins)
        left_edges = [minim]
        for _bin in range(bins):
            left_edges = left_edges + [left_edges[-1] + bin_width]
        left_edges.pop()
        expression_col = when((float(left_edges[0]) <= col(column)) 
                              & (col(column) < float(left_edges[1])), 0)
        left_edges_copy = left_edges[:]
        left_edges_copy.pop(0)
        bin_data = (df.select(col(column))
                    .na.drop()
                    .select(col(column), 
                            create_all_conditions(expression_col, 
                                                  column, 
                                                  left_edges_copy
                                                 ).alias("bin_id")
                           )
                    .groupBy("bin_id").count()
                   ).toPandas()
        
        # If no data goes into one bin, it won't 
        # appear in bin_data; so we should fill
        # in the blanks:
        bin_data.index = bin_data["bin_id"]
        new_index = list(range(bins))
        bin_data = bin_data.reindex(new_index)
        bin_data["bin_id"] = bin_data.index
        bin_data = bin_data.fillna(0)
        
        # We add the left edges and bin width:
        bin_data["left_edge"] = left_edges
        bin_data["width"] = bin_width
        
        return bin_data

    def mini_histogram(histogram_data):
        # Small histogram
        imgdata = BytesIO()
        hist_data = histogram_data
        figure = plt.figure(figsize=(2, 0.75))
        plot = plt.subplot()
        plt.bar(hist_data["left_edge"], 
                hist_data["count"], 
                width=hist_data["width"], 
                facecolor='#337ab7')
        plot.axes.get_yaxis().set_visible(False)
        plot.set_axis_bgcolor("w")
        xticks = plot.xaxis.get_major_ticks()
        for tick in xticks[1:-1]:
            tick.set_visible(False)
            tick.label.set_visible(False)
        for tick in (xticks[0], xticks[-1]):
            tick.label.set_fontsize(8)
        plot.figure.subplots_adjust(left=0.15, right=0.85, top=1, bottom=0.35, wspace=0, hspace=0)
        plot.figure.savefig(imgdata)
        imgdata.seek(0)
        result_string = 'data:image/png;base64,' + quote(base64.b64encode(imgdata.getvalue()))
        plt.close(plot.figure)
        return result_string


    def describe_integer_1d(df, column, current_result, nrows):
        if spark_version == "1.6+":
            stats_df = df.select(column).na.drop().agg(mean(col(column)).alias("mean"),
                                                       df_min(col(column)).alias("min"),
                                                       df_max(col(column)).alias("max"),
                                                       variance(col(column)).alias("variance"),
                                                       kurtosis(col(column)).alias("kurtosis"),
                                                       stddev(col(column)).alias("std"),
                                                       skewness(col(column)).alias("skewness"),
                                                       df_sum(col(column)).alias("sum")
                                                       ).toPandas()
        else:
            stats_df = df.select(column).na.drop().agg(mean(col(column)).alias("mean"),
                                                       df_min(col(column)).alias("min"),
                                                       df_max(col(column)).alias("max"),
                                                       df_sum(col(column)).alias("sum")
                                                       ).toPandas()
            stats_df["variance"] = df.select(column).na.drop().agg(variance_custom(col(column), 
                                                                                   stats_df["mean"].ix[0],
                                                                                   current_result["count"])).toPandas().ix[0][0]
            stats_df["std"] = np.sqrt(stats_df["variance"])
            stats_df["skewness"] = df.select(column).na.drop().agg(skewness_custom(col(column), 
                                                                                   stats_df["mean"].ix[0],
                                                                                   current_result["count"])).toPandas().ix[0][0]
            stats_df["kurtosis"] = df.select(column).na.drop().agg(kurtosis_custom(col(column), 
                                                                                   stats_df["mean"].ix[0],
                                                                                   current_result["count"])).toPandas().ix[0][0]

        for x in np.array([0.05, 0.25, 0.5, 0.75, 0.95]):
            stats_df[pretty_name(x)] = (df.select(column)
                                        .na.drop()
                                        .selectExpr("percentile({col},CAST({n} AS DOUBLE))"
                                                    .format(col=column, n=x)).toPandas().ix[:,0]
                                        )
        stats = stats_df.ix[0].copy()
        stats.name = column
        stats["range"] = stats["max"] - stats["min"]
        stats["iqr"] = stats[pretty_name(0.75)] - stats[pretty_name(0.25)]
        stats["cv"] = stats["std"] / float(stats["mean"])
        stats["mad"] = (df.select(column)
                        .na.drop()
                        .select(df_abs(col(column)-stats["mean"]).alias("delta"))
                        .agg(df_sum(col("delta"))).toPandas().ix[0,0] / float(current_result["count"]))
        stats["type"] = "NUM"
        stats['n_zeros'] = df.select(column).where(col(column)==0.0).count()
        stats['p_zeros'] = stats['n_zeros'] / float(nrows)

        # Large histogram
        imgdata = BytesIO()
        hist_data = create_hist_data(df, column, stats["min"], stats["max"], bins)
        figure = plt.figure(figsize=(6, 4))
        plot = plt.subplot()
        plt.bar(hist_data["left_edge"], 
                hist_data["count"], 
                width=hist_data["width"], 
                facecolor='#337ab7')
        plot.set_ylabel("Frequency")
        plot.figure.subplots_adjust(left=0.15, right=0.95, top=0.9, bottom=0.1, wspace=0, hspace=0)
        plot.figure.savefig(imgdata)
        imgdata.seek(0)
        stats['histogram'] = 'data:image/png;base64,' + quote(base64.b64encode(imgdata.getvalue()))
        #TODO Think about writing this to disk instead of caching them in strings
        plt.close(plot.figure)

        stats['mini_histogram'] = mini_histogram(hist_data)

        return stats

    def describe_float_1d(df, column, current_result, nrows):
        if spark_version == "1.6+":
            stats_df = df.select(column).na.drop().agg(mean(col(column)).alias("mean"),
                                                       df_min(col(column)).alias("min"),
                                                       df_max(col(column)).alias("max"),
                                                       variance(col(column)).alias("variance"),
                                                       kurtosis(col(column)).alias("kurtosis"),
                                                       stddev(col(column)).alias("std"),
                                                       skewness(col(column)).alias("skewness"),
                                                       df_sum(col(column)).alias("sum")
                                                       ).toPandas()
        else:
            stats_df = df.select(column).na.drop().agg(mean(col(column)).alias("mean"),
                                                       df_min(col(column)).alias("min"),
                                                       df_max(col(column)).alias("max"),
                                                       df_sum(col(column)).alias("sum")
                                                       ).toPandas()
            stats_df["variance"] = df.select(column).na.drop().agg(variance_custom(col(column), 
                                                                                   stats_df["mean"].ix[0],
                                                                                   current_result["count"])).toPandas().ix[0][0]
            stats_df["std"] = np.sqrt(stats_df["variance"])
            stats_df["skewness"] = df.select(column).na.drop().agg(skewness_custom(col(column), 
                                                                                   stats_df["mean"].ix[0],
                                                                                   current_result["count"])).toPandas().ix[0][0]
            stats_df["kurtosis"] = df.select(column).na.drop().agg(kurtosis_custom(col(column), 
                                                                                   stats_df["mean"].ix[0],
                                                                                   current_result["count"])).toPandas().ix[0][0]

        for x in np.array([0.05, 0.25, 0.5, 0.75, 0.95]):
            stats_df[pretty_name(x)] = (df.select(column)
                                        .na.drop()
                                        .selectExpr("percentile_approx({col},CAST({n} AS DOUBLE))"
                                                    .format(col=column, n=x)).toPandas().ix[:,0]
                                        )
        stats = stats_df.ix[0].copy()
        stats.name = column
        stats["range"] = stats["max"] - stats["min"]
        stats["iqr"] = stats[pretty_name(0.75)] - stats[pretty_name(0.25)]
        stats["cv"] = stats["std"] / float(stats["mean"])
        stats["mad"] = (df.select(column)
                        .na.drop()
                        .select(df_abs(col(column)-stats["mean"]).alias("delta"))
                        .agg(df_sum(col("delta"))).toPandas().ix[0,0] / float(current_result["count"]))
        stats["type"] = "NUM"
        stats['n_zeros'] = df.select(column).where(col(column)==0.0).count()
        stats['p_zeros'] = stats['n_zeros'] / float(nrows)

        # Large histogram
        imgdata = BytesIO()
        hist_data = create_hist_data(df, column, stats["min"], stats["max"], bins)
        figure = plt.figure(figsize=(6, 4))
        plot = plt.subplot()
        plt.bar(hist_data["left_edge"], 
                hist_data["count"], 
                width=hist_data["width"], 
                facecolor='#337ab7')
        plot.set_ylabel("Frequency")
        plot.figure.subplots_adjust(left=0.15, right=0.95, top=0.9, bottom=0.1, wspace=0, hspace=0)
        plot.figure.savefig(imgdata)
        imgdata.seek(0)
        stats['histogram'] = 'data:image/png;base64,' + quote(base64.b64encode(imgdata.getvalue()))
        #TODO Think about writing this to disk instead of caching them in strings
        plt.close(plot.figure)

        stats['mini_histogram'] = mini_histogram(hist_data)

        return stats        

    def describe_date_1d(df, column):
        stats_df = df.select(column).na.drop().agg(df_min(col(column)).alias("min"),
                                                   df_max(col(column)).alias("max")
                                                  ).toPandas()
        stats = stats_df.ix[0].copy()
        stats.name = column

        # Convert Pandas timestamp object to regular datetime:
        if isinstance(stats["max"], pd.tslib.Timestamp):
            stats = stats.astype(object)
            stats["max"] = str(stats["max"].to_pydatetime())
            stats["min"] = str(stats["min"].to_pydatetime())
        # Range only got when type is date
        else:
            stats["range"] = stats["max"] - stats["min"]
        stats["type"] = "DATE"
        return stats

    def describe_categorical_1d(df, column):
        value_counts = (df.select(column).na.drop()
                        .groupBy(column)
                        .agg(count(col(column)))
                        .orderBy("count({c})".format(c=column),ascending=False)
                       ).cache()
        
        # Get the most frequent class:
        stats = (value_counts
                 .limit(1)
                 .withColumnRenamed(column, "top")
                 .withColumnRenamed("count({c})".format(c=column), "freq")
                ).toPandas().ix[0]
        
        # Get the top 50 classes by value count,
        # and put the rest of them grouped at the
        # end of the Series:
        top_50 = value_counts.limit(50).toPandas()
        top_50_categories = top_50[column].values.tolist()

        others_count = pd.Series([df.select(column).na.drop()
                        .where(~(col(column).isin(*top_50_categories)))
                        .count()
                        ], index=["***Other Values***"])
        others_distinct_count = pd.Series([value_counts
                                .where(~(col(column).isin(*top_50_categories)))
                                .count()
                                ], index=["***Other Values Distinct Count***"])

        top = top_50.set_index(column)["count({c})".format(c=column)]
        top = top.append(others_count)
        top = top.append(others_distinct_count)
        stats["value_counts"] = top
        stats["type"] = "CAT"
        value_counts.unpersist()
        return stats

    def describe_constant_1d(df, column):
        stats = pd.Series(['CONST'], index=['type'], name=column)
        stats["value_counts"] = (df.select(column)
                                 .na.drop()
                                 .limit(1)).toPandas().ix[:,0].value_counts()
        return stats

    def describe_unique_1d(df, column):
        stats = pd.Series(['UNIQUE'], index=['type'], name=column)
        stats["value_counts"] = (df.select(column)
                                 .na.drop()
                                 .limit(50)).toPandas().ix[:,0].value_counts()
        return stats

    def describe_1d(df, column, nrows):
        column_type = df.select(column).dtypes[0][1]
        # TODO: think about implementing analysis for complex
        # data types:
        if ("array" in column_type) or ("stuct" in column_type) or ("map" in column_type):
            raise NotImplementedError("Column {c} is of type {t} and cannot be analyzed".format(c=column, t=column_type))

        distinct_count = df.select(column).agg(countDistinct(col(column)).alias("distinct_count")).toPandas()
        non_nan_count = df.select(column).na.drop().select(count(col(column)).alias("count")).toPandas()
        results_data = pd.concat([distinct_count, non_nan_count],axis=1)
        results_data["p_unique"] = results_data["distinct_count"] / float(results_data["count"])
        results_data["is_unique"] = results_data["distinct_count"] == nrows
        results_data["n_missing"] = nrows - results_data["count"]
        results_data["p_missing"] = results_data["n_missing"] / float(nrows)
        results_data["p_infinite"] = 0
        results_data["n_infinite"] = 0
        result = results_data.ix[0].copy()
        result["memorysize"] = 0
        result.name = column
        
        if result["distinct_count"] <= 1:
            result = result.append(describe_constant_1d(df, column))
        elif column_type in {"tinyint", "smallint", "int", "bigint"}:
            result = result.append(describe_integer_1d(df, column, result, nrows))
        elif column_type in {"float", "double", "decimal"}:
            result = result.append(describe_float_1d(df, column, result, nrows))
        elif column_type in {"date", "timestamp"}:
            result = result.append(describe_date_1d(df, column))
        elif result["is_unique"] == True:
            result = result.append(describe_unique_1d(df, column))
        else: 
            result = result.append(describe_categorical_1d(df, column))
            # Fix to also count MISSING value in the distict_count field:
            if result["n_missing"] > 0:
                result["distinct_count"] = result["distinct_count"] + 1

        # TODO: check whether it is worth it to
        # implement the "real" mode:
        if (result["count"] > result["distinct_count"] > 1):
            try:
                result["mode"] = result["top"]
            except KeyError:
                result["mode"] = 0
        else:
            try:
                result["mode"] = result["value_counts"].index[0]
            except KeyError:
                result["mode"] = 0
            # If and IndexError happens,
            # it is because all column are NULLs:
            except IndexError:
                result["mode"] = "MISSING"
            
        return result


    # Do the thing:
    ldesc = {colum: describe_1d(df, colum, table_stats["n"]) for colum in df.columns}
    
    # Compute correlation matrix
    if corr_reject is not None:
        computable_corrs = [colum for colum in ldesc if ldesc[colum]["type"] in {"NUM"}]

        if len(computable_corrs) > 0:
            corr = corr_matrix(df, columns=computable_corrs)
            for x, corr_x in corr.iterrows():
                for y, corr in corr_x.iteritems():
                    if x == y: 
                        break
                        
                    if corr >= corr_reject:
                        ldesc[x] = pd.Series(['CORR', y, corr], index=['type', 'correlation_var', 'correlation'], name=x)

    # Convert ldesc to a DataFrame
    variable_stats = pd.DataFrame(ldesc)

    # General statistics
    table_stats["nvar"] = len(df.columns)
    table_stats["total_missing"] = float(variable_stats.ix["n_missing"].sum()) / (table_stats["n"] * table_stats["nvar"])
    memsize = 0
    table_stats['memsize'] = formatters.fmt_bytesize(memsize)
    table_stats['recordsize'] = formatters.fmt_bytesize(memsize / table_stats['n'])
    table_stats.update({k: 0 for k in ("NUM", "DATE", "CONST", "CAT", "UNIQUE", "CORR")})
    table_stats.update(dict(variable_stats.loc['type'].value_counts()))
    table_stats['REJECTED'] = table_stats['CONST'] + table_stats['CORR']

    freq_dict = {}
    for var in variable_stats:
        if "value_counts" not in variable_stats[var]:
            pass
        elif not(variable_stats[var]["value_counts"] is np.nan):
            freq_dict[var] = variable_stats[var]["value_counts"]
        else:
            pass
    try:
        variable_stats = variable_stats.drop("value_counts")
    except ValueError:
        pass

    return {'table': table_stats, 'variables': variable_stats.T, 'freq': freq_dict}



def to_html(sample, stats_object):

    """
    Generate a HTML report from summary statistics and a given sample
    Parameters
    ----------
    sample: DataFrame containing the sample you want to print
    stats_object: Dictionary containing summary statistics. Should be generated with an appropriate describe() function

    Returns
    -------
    str, containing profile report in HTML format
    """

    n_obs = stats_object['table']['n']

    value_formatters = formatters.value_formatters
    row_formatters = formatters.row_formatters

    if not isinstance(sample, pd.DataFrame):
        raise TypeError("sample must be of type pandas.DataFrame")

    if not isinstance(stats_object, dict):
        raise TypeError("stats_object must be of type dict. Did you generate this using the spark_df_profiling.describe() function?")

    if set(stats_object.keys()) != {'table', 'variables', 'freq'}:
        raise TypeError("stats_object badly formatted. Did you generate this using the spark_df_profiling-eda.describe() function?")

    def fmt(value, name):
        if pd.isnull(value):
            return ""
        if name in value_formatters:
            return value_formatters[name](value)
        elif isinstance(value, float):
            return value_formatters[formatters.DEFAULT_FLOAT_FORMATTER](value)
        else:
            if sys.version_info.major == 3:
                return str(value)
            else:
                return unicode(value)

    def freq_table(freqtable, n, var_table, table_template, row_template, max_number_of_items_in_table):

        local_var_table = var_table.copy()
        freq_other_prefiltered = freqtable["***Other Values***"]
        freq_other_prefiltered_num = freqtable["***Other Values Distinct Count***"]
        freqtable = freqtable.drop(["***Other Values***", "***Other Values Distinct Count***"])

        freq_rows_html = u''

        freq_other = sum(freqtable[max_number_of_items_in_table:]) + freq_other_prefiltered
        freq_missing = var_table["n_missing"]
        max_freq = max(freqtable.values[0], freq_other, freq_missing)
        try:
            min_freq = freqtable.values[max_number_of_items_in_table]
        except IndexError:
            min_freq = 0

        # TODO: Correctly sort missing and other

        def format_row(freq, label, extra_class=''):
            width = int(freq / float(max_freq) * 99) + 1
            if width > 20:
                label_in_bar = freq
                label_after_bar = ""
            else:
                label_in_bar = "&nbsp;"
                label_after_bar = freq

            return row_template.render(label=label,
                                       width=width,
                                       count=freq,
                                       percentage='{:2.1f}'.format(freq / float(n) * 100),
                                       extra_class=extra_class,
                                       label_in_bar=label_in_bar,
                                       label_after_bar=label_after_bar)

        for label, freq in six.iteritems(freqtable[0:max_number_of_items_in_table]):
            freq_rows_html += format_row(freq, label)

        if freq_other > min_freq:
            freq_rows_html += format_row(freq_other,
                                         "Other values (%s)" % (freqtable.count() 
                                                                + freq_other_prefiltered_num 
                                                                - max_number_of_items_in_table),
                                         extra_class='other')

        if freq_missing > min_freq:
            freq_rows_html += format_row(freq_missing, "(Missing)", extra_class='missing')

        return table_template.render(rows=freq_rows_html, varid=hash(idx))

    # Variables
    rows_html = u""
    messages = []

    for idx, row in stats_object['variables'].iterrows():

        formatted_values = {'varname': idx, 'varid': hash(idx)}
        row_classes = {}

        for col, value in six.iteritems(row):
            formatted_values[col] = fmt(value, col)

        for col in set(row.index) & six.viewkeys(row_formatters):
            row_classes[col] = row_formatters[col](row[col])
            if row_classes[col] == "alert" and col in templates.messages:
                messages.append(templates.messages[col].format(formatted_values, varname = formatters.fmt_varname(idx)))

        if row['type'] == 'CAT':
            formatted_values['minifreqtable'] = freq_table(stats_object['freq'][idx], n_obs, stats_object['variables'].ix[idx],
                                                           templates.template('mini_freq_table'), templates.template('mini_freq_table_row'), 3)
            formatted_values['freqtable'] = freq_table(stats_object['freq'][idx], n_obs, stats_object['variables'].ix[idx],
                                                       templates.template('freq_table'), templates.template('freq_table_row'), 20)
            if row['distinct_count'] > 50:
                messages.append(templates.messages['HIGH_CARDINALITY'].format(formatted_values, varname = formatters.fmt_varname(idx)))
                row_classes['distinct_count'] = "alert"
            else:
                row_classes['distinct_count'] = ""

        if row['type'] == 'UNIQUE':
            obs = stats_object['freq'][idx].index

            formatted_values['firstn'] = pd.DataFrame(obs[0:3], columns=["First 3 values"]).to_html(classes="example_values", index=False)
            formatted_values['lastn'] = pd.DataFrame(obs[-3:], columns=["Last 3 values"]).to_html(classes="example_values", index=False)

            if n_obs > 40:
                formatted_values['firstn_expanded'] = pd.DataFrame(obs[0:20], index=range(1, 21)).to_html(classes="sample table table-hover", header=False)
                formatted_values['lastn_expanded'] = pd.DataFrame(obs[-20:], index=range(n_obs - 20 + 1, n_obs+1)).to_html(classes="sample table table-hover", header=False)
            else:
                formatted_values['firstn_expanded'] = pd.DataFrame(obs, index=range(1, n_obs+1)).to_html(classes="sample table table-hover", header=False)
                formatted_values['lastn_expanded'] = ''

        rows_html += templates.row_templates_dict[row['type']].render(values=formatted_values, row_classes=row_classes)

        if row['type'] in {'CORR', 'CONST'}:
            formatted_values['varname'] = formatters.fmt_varname(idx)
            messages.append(templates.messages[row['type']].format(formatted_values))


    # Overview
    formatted_values = {k: fmt(v, k) for k, v in six.iteritems(stats_object['table'])}

    row_classes={}
    for col in six.viewkeys(stats_object['table']) & six.viewkeys(row_formatters):
        row_classes[col] = row_formatters[col](stats_object['table'][col])
        if row_classes[col] == "alert" and col in templates.messages:
            messages.append(templates.messages[col].format(formatted_values, varname = formatters.fmt_varname(idx)))

    messages_html = u''
    for msg in messages:
        messages_html += templates.message_row.format(message=msg)

    overview_html = templates.template('overview').render(values=formatted_values, row_classes = row_classes, messages=messages_html)

    # Sample

    sample_html = templates.template('sample').render(sample_table_html=sample.to_html(classes="sample"))
    # TODO: should be done in the template
    return templates.template('base').render({'overview_html': overview_html, 'rows_html': rows_html, 'sample_html': sample_html})