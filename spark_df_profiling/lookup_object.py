class BaseLookupObject(object):
    """
    Base class for a lookup object, its a class that takes in a dataframe column, and looks up all its values in an
    external database or DataFrame.
    """

    def __init__(self):
        """
        Define Database object or DataFrame path here
        """
        pass

    def lookup(self, input_col_df, col_name_in_db=None):
        """
        Look up all values in given DF in a database or DataFrame
        :param input_col_df: A DataFrame column to look up. This MUST contain only 1 column
        :param col_name_in_db: The name of the column to use in the lookup db, if this is None, its assumed to be the
        same name as the input column
        :return: Two DataFrames, one with matched rows and one with unmatched rows
        """
        pass


class DataFrameLookupObject(BaseLookupObject):
    """
    Lookup class that uses a DataFrame as the lookup DB
    """

    def __init__(self, db_df):
        super(DataFrameLookupObject, self).__init__()
        self.db = db_df

    def lookup(self, input_col_df, col_name_in_db=None):
        assert len(input_col_df.columns) == 1
        colname = input_col_df.columns[0]
        col_name_in_db = col_name_in_db if col_name_in_db else colname
        joined_values = input_col_df.join(self.db, input_col_df[colname] == self.db[col_name_in_db], 'inner').drop(
            self.db[col_name_in_db])  # the drop is because join duplicates the joined column, see https://docs.databricks.com/spark/latest/faq/join-two-dataframes-duplicated-column.html
        diff = input_col_df.subtract(joined_values.select(colname))
        debug2 = diff.collect()
        return joined_values, diff
