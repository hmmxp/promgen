import json
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from promgen import models, prometheus


_RULES = '''
# Service: Service 1
# Service URL: /service/1/
ALERT RuleName
  IF up==0
  FOR 1s
  LABELS {severity="severe"}
  ANNOTATIONS {service="http://example.com/service/1/", summary="Test case"}


'''.lstrip()


class RuleTest(TestCase):
    @mock.patch('django.db.models.signals.post_save', mock.Mock())
    def setUp(self):
        self.shard = models.Shard.objects.create(name='Shard 1')
        self.service = models.Service.objects.create(id=1, name='Service 1', shard=self.shard)
        self.rule = models.Rule.objects.create(
            name='RuleName',
            clause='up==0',
            duration='1s',
            service=self.service
        )
        models.RuleLabel.objects.create(name='severity', value='severe', rule=self.rule)
        models.RuleAnnotation.objects.create(name='summary', value='Test case', rule=self.rule)

    @mock.patch('django.db.models.signals.post_save')
    def test_write(self, mock_render):
        result = prometheus.render_rules()
        self.assertEqual(result, _RULES)

    @mock.patch('django.db.models.signals.post_save')
    def test_copy(self, mock_render):
        service = models.Service.objects.create(name='Service 2', shard=self.shard)
        copy = self.rule.copy_to(service)
        # Test that our copy has the same labels and annotations
        self.assertIn('severity', copy.labels())
        self.assertIn('summary', copy.annotations())
        # and test that we actually duplicated them and not moved them
        self.assertEqual(models.RuleLabel.objects.count(), 2)
        self.assertEqual(models.RuleAnnotation.objects.count(), 2)

    @mock.patch('django.db.models.signals.post_save')
    def test_import(self, mock_render):
        self.client.post(reverse('import'), {
            'rules': json.dumps([{
                'service': 'Service 1',
                'name': 'ImportRule',
                'duration': '1s',
                'labels': {
                    'severity': 'severe',
                },
                'annotations': {
                    'summary': 'Test case'
                }
            }])
        })

        rule = models.Rule.objects.filter(name='ImportRule').get()
        self.assertEqual(models.RuleLabel.objects.filter(rule=rule).count(), 1, 'Missing labels')
        self.assertEqual(models.RuleAnnotation.objects.filter(rule=rule).count(), 1, 'Missing annotations')
        # Cleanup to avoid test_write errors
        #rules.delete()
