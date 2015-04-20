import os
import unittest
import shutil
import test.lib.test_util as util
import test.lib.test_helper as test_helper
from test.lib.test_helper import MavensMateTest

base_test_directory = test_helper.base_test_directory

class StackTraceAndLogsTest(MavensMateTest):
    
    def test_01_should_delete_trace_flags(self): 
        test_helper.create_project(self, "unit test tooling project")
        stdin = {
            "project_name"      : "unit test tooling project"
        }
        mm_response = self.runCommand('delete_trace_flags', stdin)
        self.assertTrue(mm_response['success'] == True)

    def test_02_should_create_new_trace_flag(self): 
        stdin = {
            "project_name"      : "unit test tooling project",
            "type"              : "user",
            "debug_categories"  : {
                "ApexCode"      : "DEBUG",
                "Visualforce"   : "INFO"
            }
        }
        mm_response = self.runCommand('new_log', stdin)
        self.assertTrue(mm_response['success'] == True)
        self.assertTrue('id' in mm_response and len(mm_response['id']) is 18)

    def test_03_should_create_new_quicklog(self): 
        # need to delete existing trace flag first (since there
        # can only be one TraceLog per TracedEntityId), NB: in 
        # some cases salesforce doesn't seem to check this, but 
        # it's not consistent
        stdin = {
            "project_name"      : "unit test tooling project"
        }
        mm_response = self.runCommand('delete_trace_flags', stdin)
        self.assertTrue(mm_response['success'] == True)
        
        stdin = {
            "project_name"      : "unit test tooling project",
            "type"              : "user",
            "debug_categories"  : {
                "ApexCode"      : "DEBUG",
                "Visualforce"   : "INFO"
            }
        }
        mm_response = self.runCommand('new_quick_log', stdin)
        self.assertTrue(mm_response['success'] == True)
        # self.assertTrue('1 Log(s) created successfully' in mm_response['body'])

    def test_04_should_get_trace_flags(self): 
        stdin = {
            "project_name"      : "unit test tooling project"
        }
        mm_response = self.runCommand('get_trace_flags', stdin)
        self.assertTrue(mm_response['totalSize'] == 1)
        self.assertTrue(mm_response['entityTypeName'] == 'TraceFlag')
        self.assertTrue(mm_response['done'] == True)

    def test_05_should_update_debug_settings(self): 
        stdin = {
            "project_name"      : "unit test tooling project",
            "debug_categories"  : {
                "Workflow"      : "FINE", 
                "Callout"       : "FINE", 
                "System"        : "FINE", 
                "Database"      : "FINE", 
                "ApexCode"      : "FINE", 
                "Validation"    : "FINE", 
                "Visualforce"   : "FINE"
            },
            "expiration"        : 120
        }
        mm_response = self.runCommand('update_debug_settings', stdin)
        new_debug_settings = util.parse_json_file(os.path.join(base_test_directory, "test_workspace", stdin["project_name"], "config", ".debug"))
        self.assertTrue(new_debug_settings['expiration'] == stdin["expiration"])
        self.assertTrue(new_debug_settings['levels']['Workflow'] == stdin["debug_categories"]["Workflow"])
        self.assertTrue(new_debug_settings['levels']['Visualforce'] == stdin["debug_categories"]["Visualforce"])

    def test_06_should_fetch_logs(self): 
        stdin = {
            "project_name"      : "unit test tooling project"
        }
        mm_response = self.runCommand('fetch_logs', stdin)
        self.assertTrue(mm_response['success'] == True)

    @classmethod    
    def tearDownClass(self):
        if os.path.exists(os.path.join(base_test_directory,"test_workspace","unit test tooling project")):
           shutil.rmtree(os.path.join(base_test_directory,"test_workspace","unit test tooling project"))
        #pass

if __name__ == '__main__':
    if os.path.exists(os.path.join(base_test_directory,"test_workspace","unit test tooling project")):
        shutil.rmtree(os.path.join(base_test_directory,"test_workspace","unit test tooling project"))
    unittest.main()