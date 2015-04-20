#TO RUN: joey2 project_operation_tests.py
import os
import unittest
import shutil
import test.lib.test_util as util
import test.lib.test_helper as test_helper
from test.lib.test_helper import MavensMateTest

class CheckpointTests(MavensMateTest):
 
    def test_01_should_create_new_stack_trace(self): 
        test_helper.create_project(self, "unit test tooling project")
        pass
        
        # test is a duplicate of StackTraceAndLogsTest.test_02_should_create_new_trace_flag (/functional/debug/log_tests.py)
        # removed due to issues with trace flag request failing if 
        # there is already a similar trace flag (can be fixed by 
        # first deleting existing trace flags before trying to create 
        # a new one)
        
        # stdin = {
        #     "project_name"      : "unit test tooling project",
        #     "type"              : "user",
        #     "debug_categories"  : {
        #         "ApexCode"      : "DEBUG",
        #         "Visualforce"   : "DEBUG"
        #     }
        # }
        # mm_response = self.runCommand('new_log', stdin)        
        # self.assertEqual(mm_response['success'],True)
        # self.assertTrue('id' in mm_response and len(mm_response['id']) is 18)

    def test_02_should_delete_all_apex_checkpoints(self):
        stdin = {
            "project_name"      : "unit test tooling project",
        }
        mm_response = self.runCommand('delete_all_apex_checkpoints', stdin)
        self.assertEqual(mm_response['success'],True)

    def test_03_should_create_new_apex_checkpoint(self): 
        ###CREATE APEX CLASS
        stdin = {
            'project_name' : 'unit test tooling project',
            'metadata_type': 'ApexClass', 
            'params': {'api_name': 'unittesttoolingapexclass'}, 
            'github_template': {
                'author': 'MavensMate', 
                'name': 'Default', 
                'description': 'The default template for an Apex Class', 
                'file_name': 'ApexClass.cls', 
                'params': [
                    {
                        'default': 'MyApexClass', 
                        'name': 'api_name', 
                        'description': 'Apex Class API Name'
                    }
                ]
            }
        }

        mm_response = self.runCommand('new_metadata', stdin)        
        
        if 'success' in mm_response and mm_response['success']:
            self.assertTrue(mm_response['success'] == True)
            self.assertTrue('id' in mm_response and len(mm_response['id']) is 18)
        elif 'success' in mm_response and not mm_response['success']:
            if 'body' in mm_response and mm_response['body'] == 'This API name is already in use in your org.':
                # probably by accident, this is ok bc we clean it up at the end
                pass
        
        ###CREATE CHECKPOINT
        stdin = {
            "project_name"      : "unit test tooling project",
            "IsDumpingHeap"     : True, 
            "Iteration"         : 1, 
            "Object_Type"       : "ApexClass", 
            "Line"              : 1,
            "ActionScriptType"  : "None", 
            "API_Name"          : "unittesttoolingapexclass"
        }
        mm_response = self.runCommand('new_apex_overlay', stdin)        
        self.assertEqual(mm_response['success'],True)

    def test_04_should_fetch_checkpoint(self): 
        stdin = {
            "project_name"      : "unit test tooling project",
        }
        mm_response = self.runCommand('fetch_checkpoints', stdin)
        self.assertEqual(mm_response['success'],True)  

        ###DELETE CLASS
        client_settings = util.parse_json_from_file(os.path.join(test_helper.base_test_directory,"lib","user_client_settings.json"))
        stdin = {
            "files": [os.path.join(client_settings["mm_workspace"],"unit test tooling project","src","classes","unittesttoolingapexclass.cls")], 
            "project_name": "unit test tooling project"
        }
        mm_response = self.runCommand('delete', stdin)        
        self.assertEqual(mm_response['success'],True)  

    @classmethod    
    def tearDownClass(self):
        if os.path.exists(os.path.join(test_helper.base_test_directory,"test_workspace","unit test tooling project")):
            shutil.rmtree(os.path.join(test_helper.base_test_directory,"test_workspace","unit test tooling project"))

if __name__ == '__main__':
    if os.path.exists(os.path.join(test_helper.base_test_directory,"test_workspace","unit test tooling project")):
        shutil.rmtree(os.path.join(test_helper.base_test_directory,"test_workspace","unit test tooling project"))
    unittest.main()