# coding: utf-8
from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

import json
import validators
from itertools import chain

from jinja2 import Template
from jenkins import Jenkins
from errbot import BotPlugin, botcmd, webhook
from errbot.utils import ValidationException

try:
    from config import JENKINS_URL, JENKINS_USERNAME, JENKINS_PASSWORD
except ImportError:
    # Default mandatory configuration
    JENKINS_URL = ''
    JENKINS_USERNAME = ''
    JENKINS_PASSWORD = ''

try:
    from config import (JENKINS_RECEIVE_NOTIFICATION,
                        JENKINS_CHATROOMS_NOTIFICATION)
except ImportError:
    # Default optional configuration
    JENKINS_RECEIVE_NOTIFICATION = True
    JENKINS_CHATROOMS_NOTIFICATION = ()


CONFIG_TEMPLATE = {
    'URL': JENKINS_URL,
    'USERNAME': JENKINS_USERNAME,
    'PASSWORD': JENKINS_PASSWORD,
    'RECEIVE_NOTIFICATION': JENKINS_RECEIVE_NOTIFICATION,
    'CHATROOMS_NOTIFICATION': JENKINS_CHATROOMS_NOTIFICATION}

JENKINS_JOB_TEMPLATE_PIPELINE = """<?xml version='1.0' encoding='UTF-8'?>
<flow-definition plugin="workflow-job">
  <actions/>
  <description></description>
  <keepDependencies>false</keepDependencies>
  <properties/>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition" plugin="workflow-cps">
    <scm class="hudson.plugins.git.GitSCM" plugin="git">
      <configVersion>2</configVersion>
      <userRemoteConfigs>
        <hudson.plugins.git.UserRemoteConfig>
          <url>{repository}</url>
        </hudson.plugins.git.UserRemoteConfig>
      </userRemoteConfigs>
      <branches>
        <hudson.plugins.git.BranchSpec>
          <name>*/master</name>
        </hudson.plugins.git.BranchSpec>
      </branches>
      <doGenerateSubmoduleConfigurations>false</doGenerateSubmoduleConfigurations>
      <submoduleCfg class="list"/>
      <extensions/>
    </scm>
    <scriptPath>Jenkinsfile</scriptPath>
  </definition>
  <triggers/>
</flow-definition>
"""


class JenkinsBot(BotPlugin):
    """Basic Err integration with Jenkins CI"""

    min_err_version = '1.2.1'
    # max_err_version = '3.3.0'

    def get_configuration_template(self):
        return CONFIG_TEMPLATE

    def configure(self, configuration):
        if configuration is not None and configuration != {}:
            config = dict(chain(CONFIG_TEMPLATE.items(),
                                configuration.items()))
        else:
            config = CONFIG_TEMPLATE
        super(JenkinsBot, self).configure(config)
        return

    def check_configuration(self, configuration):
        self.log.debug(configuration)
        for c in configuration:
            if c == 'URL':
                if not validators.url(configuration['URL']):
                    raise ValidationException('JENKINS_URL is not a well formed URL')
            elif c in ['USERNAME', 'PASSWORD', 'RECEIVE_NOTIFICATION']:
                if len(configuration[c]) == 0 or not isinstance(configuration[c], str):
                    raise ValidationException("{} is a required string config setting".format(c))
            elif c in ['CHATROOMS_NOTIFICATION']:
                if not isinstance(configuration[c], tuple):
                    raise ValidationException("{} should be of type tuple".format(c))
        return

    def connect_to_jenkins(self):
        """Connect to a Jenkins instance using configuration."""
        self.log.debug('Connecting to Jenkins ({0})'.format(
            self.config['URL']))
        self.jenkins = Jenkins(url=self.config['URL'],
                               username=self.config['USERNAME'],
                               password=self.config['PASSWORD'])
        return

    def broadcast(self, mess):
        """Shortcut to broadcast a message to all elligible chatrooms."""
        chatrooms = (self.config['CHATROOMS_NOTIFICATION']
                     if self.config['CHATROOMS_NOTIFICATION']
                     else self.bot_config.CHATROOM_PRESENCE)

        for room in chatrooms:
            self.send(self.build_identifier(room),
                      mess,
                      message_type='groupchat')
        return

    @webhook(r'/jenkins/notification')
    def handle_notification(self, incoming_request):
        if not self.config['RECEIVE_NOTIFICATION']:
            return "Notification handling is disabled \
                    (JENKINS_RECEIVE_NOTIFICATION = False)"

        self.log.debug(repr(incoming_request))
        self.broadcast(self.format_notification(incoming_request))
        return "OK"

    @botcmd
    def jenkins_list(self, mess, args):
        """List all jobs, optionally filter them using a search term."""
        self.connect_to_jenkins()
        return self.format_jobs(self.jenkins.get_jobs(folder_depth=None))

    @botcmd
    def jenkins_running(self, mess, args):
        """List all running jobs."""
        self.connect_to_jenkins()

        jobs = [job for job in self.jenkins.get_jobs()
                if 'anime' in job['color']]
        return self.format_running_jobs(jobs)

    @botcmd(split_args_with=None)
    def jenkins_param(self, mess, args):
        """List Parameters for a given job."""
        if len(args) == 0:
            return 'What Job would you like the parameters for?'

        self.connect_to_jenkins()

        job = self.jenkins.get_job_info(args[0])
        if job['actions'][1] != {}:
            job_param = job['actions'][1]['parameterDefinitions']
        elif job['actions'][0] != {}:
            job_param = job['actions'][0]['parameterDefinitions']
        else:
            job_param = []

        return self.format_params(job_param)

    @botcmd(split_args_with=None)
    def jenkins_build(self, mess, args):
        """Build a Jenkins Job with the given parameters
        Example: !jenkins build test_project FOO:bar
        """
        if len(args) == 0:  # No Job name
            return 'What job would you like to build?'

        self.connect_to_jenkins()
        params = self.build_parameters(args[1:])

        # Is it a parameterized job ?
        job = self.jenkins.get_job_info(args[0])
        if job['actions'][0] == {} and job['actions'][1] == {}:
            self.jenkins.build_job(args[0])
        else:
            self.jenkins.build_job(args[0], params)

        running_job = self.search_job(args[0])
        return 'Your job should begin shortly: {0}'.format(
            self.format_jobs(running_job))

    @botcmd(split_args_with=None)
    def build(self, mess, args):
        """Shortcut for jenkins_build"""
        return self.jenkins_build(mess, args)

    @botcmd(split_args_with=None)
    def jenkins_create(self, mess, args):
        """Create a Jenkins Job.
        Example: !jenkins create pipeline foo git@github.com:foo/bar.git
        """
        if len(args) < 2:  # No Job type or name
            return 'Oops, I need a type and a name for your new job.'

        if args[0] not in ('pipeline', 'multibranch'):
            return 'I\'m sorry, what type of job do you want ?'

        self.connect_to_jenkins()

        if args[0] == 'pipeline':
            self.jenkins.create_job(
                args[1],
                JENKINS_JOB_TEMPLATE_PIPELINE.format(repository=args[2]))
        elif args[0] == 'multibranch':
            return
        return

    def search_job(self, search_term):
        self.log.debug('Querying Jenkins for job "{0}"'.format(search_term))
        return [job for job in self.jenkins.get_jobs(folder_depth=None)
                if search_term.lower() == job['fullname'].lower()]

    def format_running_jobs(self, jobs):
        if len(jobs) == 0:
            return 'No running jobs.'

        jobs_info = [self.jenkins.get_job_info(job['name']) for job in jobs]
        return '\n\n'.join(['%s (%s)\n%s' % (
            job['name'],
            job['lastBuild']['url'],
            job['healthReport'][0]['description'])
                            for job in jobs_info]).strip()

    @staticmethod
    def format_jobs(jobs):
        if len(jobs) == 0:
            return 'No jobs found.'

        max_length = max([len(job['fullname']) for job in jobs])
        return '\n'.join(
            ['%s (%s)' % (job['fullname'].ljust(max_length), job['url'])
             for job in jobs]).strip()

    @staticmethod
    def format_params(job):
        """Format job parameters."""
        if len(job) == 0:
            return 'This job is not parameterized.'
        PARAM_TEMPLATE = Template("""{% for p in params %}Type: {{p.type}}
Description: {{p.description}}
Default Value: {{p.defaultParameterValue.value}}
Parameter Name: {{p.name}}

{% endfor %}""")
        return PARAM_TEMPLATE.render({'params': job})

    @staticmethod
    def format_notification(body):
        body['fullname'] = body.get('fullname', body['name'])
        NOTIFICATION_TEMPLATE = Template("""Build #{{build.number}} \
{{build.status}} for Job {{fullname}} ({{build.full_url}})
{% if build.scm %}Based on {{build.scm.url}}/commit/{{build.scm.commit}} \
({{build.scm.branch}}){% endif %}""")
        return NOTIFICATION_TEMPLATE.render(body)

    @staticmethod
    def build_parameters(params):
        if len(params) > 0:
            return {param.split(':')[0]: param.split(':')[1]
                    for param in params}
        return {'': ''}
