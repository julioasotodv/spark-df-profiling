
import codecs
import os
from .templates import template
from .base import describe, to_html

NO_OUTPUTFILE = "spark_df_profiling.no_outputfile"
DEFAULT_OUTPUTFILE = "spark_df_profiling.default_outputfile"


class ProfileReport(object):
    html = ''
    file = None

    def __init__(self, df, bins=10, sample=5, corr_reject=0.9, config={}, **kwargs):

        sample = df.limit(sample).toPandas()

        description_set = describe(df, bins=bins, corr_reject=corr_reject, config=config, **kwargs)

        self.html = to_html(sample,
                            description_set)

        self.description_set = description_set

    def render_standalone(self, mode="databricks", utils=None):
        if mode != "databricks":
            raise NotImplementedError("Only databricks mode is supported for now")
        else:
            library_path = os.path.abspath(os.path.dirname(__file__))
            css_path=os.path.join(library_path,'templates/css/')
            js_path=os.path.join(library_path,'templates/js/')
            utils.fs.mkdirs("/FileStore/spark_df_profiling/css")
            utils.fs.mkdirs("/FileStore/spark_df_profiling/js")
            utils.fs.cp("file:" + css_path + "bootstrap-theme.min.css", 
                        "/FileStore/spark_df_profiling/css/bootstrap-theme.min.css")
            utils.fs.cp("file:" + css_path + "bootstrap.min.css", 
                        "/FileStore/spark_df_profiling/css/bootstrap.min.css")
            utils.fs.cp("file:" + js_path  + "bootstrap.min.js", 
                        "/FileStore/spark_df_profiling/js/bootstrap.min.js")
            utils.fs.cp("file:" + js_path  + "jquery.min.js", 
                        "/FileStore/spark_df_profiling/js/jquery.min.js")
            return template('wrapper_static').render(content=self.html)

    def get_description(self):
        return self.description_set

    def get_rejected_variables(self, threshold=0.9):
        """ return a list of variable names being rejected for high
            correlation with one of remaining variables

            Parameters:
            ----------
            threshold: float (optional)
                correlation value which is above the threshold are rejected
        """
        variable_profile = self.description_set['variables']
        return variable_profile.index[variable_profile.correlation > threshold].tolist()

    def to_file(self, outputfile=DEFAULT_OUTPUTFILE):
        if outputfile != NO_OUTPUTFILE:
            if outputfile == DEFAULT_OUTPUTFILE:
                outputfile = 'profile_' + str(hash(self)) + ".html"

            self.file = codecs.open(outputfile, 'w+b', encoding='utf8')
            # TODO: should be done in the template
            self.file.write(self.rendered_html())
            self.file.close()

    def rendered_html(self):
        return template('wrapper').render(content=self.html)

    def _repr_html_(self):
        return self.html

    def __str__(self):
        return "Output written to file " + str(self.file.name)



