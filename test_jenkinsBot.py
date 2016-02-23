import jenkinsBot


class TestJenkinsBot(object):
    extra_plugin_dir = '.'


class TestJenkinsBotStaticMethods(object):

    def test_format_jobs_helper(self):
        jobs = [{'name': 'foo',
                 'fullname': 'foo bar',
                 'url': 'http://jenkins.example.com/job/foo/'}]
        result = jenkinsBot.JenkinsBot.format_jobs(jobs)
        assert result == 'foo (http://jenkins.example.com/job/foo/)'

    def test_format_jobs_helper_no_params(self):
        jobs = []
        result = jenkinsBot.JenkinsBot.format_jobs(jobs)
        assert result == 'No jobs found.'

    def test_format_params_helper(self):
        params = [{
            'defaultParameterValue': {'value': 'bar'},
            'description': 'foo bar baz',
            'name': 'FOO',
            'type': 'StringParameterDefinition'
        }]
        result = jenkinsBot.JenkinsBot.format_params(params)
        assert result == """Type: StringParameterDefinition
Description: foo bar baz
Default Value: bar
Parameter Name: FOO
_
"""

    def test_build_parameters_helper(self):
        params = ['FOO:bar', 'BAR:baz']
        result = jenkinsBot.JenkinsBot.build_parameters(params)
        assert result == {'FOO': 'bar', 'BAR': 'baz'}

    def test_build_parameters_helper_no_params(self):
        params = []
        result = jenkinsBot.JenkinsBot.build_parameters(params)
        assert result == {'': ''}