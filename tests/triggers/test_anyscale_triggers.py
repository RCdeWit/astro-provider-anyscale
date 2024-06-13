import unittest
from unittest.mock import patch, MagicMock
import asyncio
from datetime import datetime
import os
import pytest
from typing import Any, Dict, AsyncIterator, Tuple, Optional
from pathlib import Path
from airflow.exceptions import AirflowNotFoundException

from anyscale.job.models import JobState
from anyscale.service.models import ServiceState

from anyscale_provider.hooks.anyscale import AnyscaleHook
from anyscale_provider.triggers.anyscale import AnyscaleJobTrigger, AnyscaleServiceTrigger
from airflow.triggers.base import TriggerEvent
from airflow.models.connection import Connection

class TestAnyscaleJobTrigger(unittest.TestCase):
    def setUp(self):
        self.trigger = AnyscaleJobTrigger(conn_id='anyscale_default',
                                          job_id='123',
                                          job_start_time=datetime.now().timestamp())

    @patch('anyscale_provider.triggers.anyscale.AnyscaleJobTrigger.get_current_status')
    def test_is_terminal_status(self, mock_get_status):
        mock_get_status.return_value = 'SUCCEEDED'
        self.assertTrue(self.trigger.is_terminal_status('123'))

    @patch('anyscale_provider.triggers.anyscale.AnyscaleJobTrigger.get_current_status')
    def test_is_not_terminal_status(self, mock_get_status):
        mock_get_status.return_value = 'RUNNING'
        self.assertFalse(self.trigger.is_terminal_status('123'))

    @patch('asyncio.sleep', return_value=None)
    @patch('anyscale_provider.triggers.anyscale.AnyscaleJobTrigger.get_current_status', side_effect=['RUNNING', 'RUNNING', 'SUCCEEDED'])
    async def test_run_successful_completion(self, mock_get_status, mock_sleep):
        events = []
        async for event in self.trigger.run():
            events.append(event)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['status'], 'SUCCEEDED')

    @patch('time.time', side_effect=[100, 200, 300, 400, 10000])  # Simulating time passing and timeout
    @patch('asyncio.sleep', return_value=None)
    async def test_run_timeout(self, mock_sleep, mock_time):
        events = []
        async for event in self.trigger.run():
            events.append(event)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['status'], 'timeout')

    @patch('anyscale_provider.triggers.anyscale.AnyscaleJobTrigger.is_terminal_status', side_effect=Exception("Error occurred"))
    async def test_run_exception(self, mock_is_terminal_status):
        events = []
        async for event in self.trigger.run():
            events.append(event)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['status'], JobState.FAILED)
        self.assertIn('Error occurred', events[0]['message'])

    @patch('anyscale_provider.hooks.anyscale.AnyscaleHook.get_job_status')
    async def test_get_current_status(self, mock_get_job_status):
        mock_get_job_status.return_value = MagicMock(state=JobState.SUCCEEDED)
        trigger = AnyscaleJobTrigger(conn_id='default_conn',
                                     job_id='',
                                     job_start_time=datetime.now().timestamp())
        events = []
        async for event in trigger.run():
            events.append(event)
        
        status = self.trigger.get_current_status('123')
        self.assertEqual(status, JobState.SUCCEEDED)
        mock_get_job_status.assert_called_once_with(job_id='123')

    async def test_run_no_job_id_provided(self):
        trigger = AnyscaleJobTrigger(conn_id='default_conn',
                                     job_id='',
                                     job_start_time=datetime.now().timestamp())
        events = []
        async for event in trigger.run():
            events.append(event)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['status'], 'error')
        self.assertIn('No job_id provided', events[0]['message'])
    
    @patch('airflow.models.connection.Connection.get_connection_from_secrets')
    def test_hook_method(self, mock_get_connection):
        # Configure the mock to raise AirflowNotFoundException
        mock_get_connection.side_effect = AirflowNotFoundException("The conn_id `default_conn` isn't defined")

        trigger = AnyscaleJobTrigger(conn_id='default_conn',
                                     job_id='123',
                                     job_start_time=datetime.now().timestamp())
        
        with self.assertRaises(AirflowNotFoundException) as context:
            result = trigger.hook()

        self.assertIn("The conn_id `default_conn` isn't defined", str(context.exception))
    
    def test_serialize(self):
        time = datetime.now().timestamp()
        trigger = AnyscaleJobTrigger(conn_id='default_conn',
                                     job_id='123',
                                     job_start_time=time)
        
        result = trigger.serialize()
        expected_output = ("anyscale_provider.triggers.anyscale.AnyscaleJobTrigger", {
            "conn_id": 'default_conn',
            "job_id": '123',
            "job_start_time": time,
            "poll_interval": 60,
            "timeout": 3600
        })

        # Check if the result is a tuple
        self.assertTrue(isinstance(result, tuple))
        
        # Check if the tuple contains a string and a dictionary
        self.assertTrue(isinstance(result[0], str))
        self.assertTrue(isinstance(result[1], dict))
        
        # Check if the result matches the expected output
        self.assertEqual(result, expected_output)

class TestAnyscaleServiceTrigger(unittest.TestCase):
    def setUp(self):
        self.trigger = AnyscaleServiceTrigger(conn_id='default_conn',
                                              service_name='service123',
                                              expected_state='RUNNING',
                                              canary_percent=None)

    @patch('anyscale_provider.triggers.anyscale.AnyscaleServiceTrigger.get_current_status')
    def test_check_current_status(self, mock_get_status):
        mock_get_status.return_value = "STARTING"
        self.assertTrue(self.trigger.check_current_status('service123'))

    @patch('asyncio.sleep', return_value=None)
    @patch('anyscale_provider.triggers.anyscale.AnyscaleServiceTrigger.get_current_status', side_effect=['STARTING', 'UPDATING', 'RUNNING'])
    async def test_run_successful(self, mock_get_status, mock_sleep):
        events = []
        async for event in self.trigger.run():
            events.append(event)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['status'], ServiceState.RUNNING)
        self.assertIn('Service deployment succeeded', events[0]['message'])

    @patch('time.time', side_effect=[100, 200, 300, 400, 10000])  # Simulating time passing and timeout
    @patch('asyncio.sleep', return_value=None)
    async def test_run_timeout(self, mock_sleep, mock_time):
        events = []
        async for event in self.trigger.run():
            events.append(event)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['status'], ServiceState.UNKNOWN)
        self.assertIn('did not reach RUNNING within the timeout period', events[0]['message'])

    @patch('anyscale_provider.triggers.anyscale.AnyscaleServiceTrigger.check_current_status', side_effect=Exception("Error occurred"))
    async def test_run_exception(self, mock_check_current_status):
        events = []
        async for event in self.trigger.run():
            events.append(event)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['status'], ServiceState.SYSTEM_FAILURE)
        self.assertIn('Error occurred', events[0]['message'])

if __name__ == '__main__':
    unittest.main()