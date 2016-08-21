
import codecs
from .templates import template
from .base import describe, to_html

NO_OUTPUTFILE = "spark_df_profiling.no_outputfile"
DEFAULT_OUTPUTFILE = "spark_df_profiling.default_outputfile"


class ProfileReport(object):
    html = ''
    file = None

    def __init__(self, df, bins=10, sample=5, corr_reject=0.9, **kwargs):

        sample = df.limit(sample).toPandas()

        description_set = describe(df, bins=bins, corr_reject=corr_reject, **kwargs)

        self.html = to_html(sample,
                            description_set)

        self.description_set = description_set

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
            self.file.write(templates.template('wrapper').render(content=self.html))
            self.file.close()

    def _repr_html_(self):
        return self.html

    def __str__(self):
        return "Output written to file " + str(self.file.name)



