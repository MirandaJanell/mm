import re
import sys
import traceback
import json
import os
import mm.util as util
import mm.config as config
import shutil
import mm.xmltodict as xmltodict
import threading
import time
import datetime
import collections
import webbrowser
import mm.crawlJson as crawlJson
import xml.parsers.expat
from mm.local_store import ConflictManager
from mm.health_check import HealthCheck
from xml.dom import minidom
from mm.exceptions import *
from operator import itemgetter
from mm.sfdc_client import MavensMateClient
sys.path.append('../')

debug = config.logger.debug

def setup():
    config.project = MavensMateProject(params)

class MavensMateProject(object):

    def __init__(self, params={}, **kwargs):
        params = dict(params.items() + kwargs.items())
        self.deferred_project_commands = ['new_project', 'new_project_from_existing_directory', 'get_active_session']
        self.ui_commands_that_require_client = ['debug_log']
        self.sfdc_session       = None
        self.id                 = params.get('id', None)
        self.project_name       = params.get('project_name', None)
        self.username           = params.get('username', None)
        self.password           = params.get('password', None)
        self.org_type           = params.get('org_type', 'Developer')
        self.org_url            = params.get('org_url', None)
        self.package            = params.get('package', None)
        self.ui                 = params.get('ui', False)
        self.directory          = params.get('directory', False)
        self.sfdc_client        = None
        self.defer_connection   = params.get('defer_connection', False)
        self.subscription       = params.get('subscription', [])
        self.location           = None
        self.conflict_manager   = None
        if config.connection.operation not in self.deferred_project_commands and self.project_name == None: #=> existing project on the disk
            config.connection.workspace = os.path.abspath(os.path.join(os.getcwd(), os.pardir))
            self.project_name = os.path.basename(os.getcwd())

        if config.connection.operation not in self.deferred_project_commands and self.project_name != None and os.path.exists(os.path.join(config.connection.workspace,self.project_name)): #=> existing project on the disk
            self.location                   = os.path.join(config.connection.workspace,self.project_name)
            self.settings                   = self.__get_settings()
            self.project_name               = self.settings.get('project_name', os.path.basename(self.location))
            self.sfdc_session               = self.__get_sfdc_session()
            self.package                    = os.path.join(self.location,"src","package.xml")
            self.is_metadata_indexed        = self.get_is_metadata_indexed()
            if self.subscription == []:
                self.subscription           = self.settings.get('subscription', [])
            self.conflict_manager = ConflictManager(self)
            
            if not config.offline:
                if (self.ui == False and self.defer_connection == False) or config.connection.operation in self.ui_commands_that_require_client:
                    needs_session_override = False
                    if self.sfdc_session != None and 'endpoint' in self.sfdc_session:
                        endpoint = self.sfdc_session['endpoint']
                        api_version_preference = int(float(util.SFDC_API_VERSION))
                        if int(float(endpoint.split("/")[-1])) != api_version_preference:
                            needs_session_override = True

                    self.sfdc_client = MavensMateClient(credentials=self.get_creds(),override_session=needs_session_override)

                    if self.sfdc_session != None and 'sid' in self.sfdc_session and self.sfdc_client != None and (self.sfdc_session['sid'] != self.sfdc_client.sid): 
                        config.logger.debug('storing updated session information locally')
                        self.__set_sfdc_session()
                    elif self.sfdc_session == None:
                        config.logger.debug('storing new session information locally')
                        self.__set_sfdc_session()
                    elif 'server_url' not in self.sfdc_session:
                        config.logger.debug('storing new session information locally because of missing server_url')
                        self.__set_sfdc_session()
                    elif self.sfdc_client.reset_creds == True:
                        config.logger.debug('storing new session information locally because reset_creds')
                        self.__set_sfdc_session()

        elif config.connection.operation not in self.deferred_project_commands and self.project_name != None and not os.path.exists(os.path.join(config.connection.workspace,self.project_name)):
            raise MMException('Project not found in your workspace')

    #used to create a new project in a workspace
    def retrieve_and_write_to_disk(self,action='new'):
        debug('>>>>>> ')
        debug(os.path.join(config.connection.workspace,self.project_name))
        if os.path.isdir(os.path.join(config.connection.workspace,self.project_name)) and action == 'new':
            raise MMException('A project with this name already exists in your workspace. To create a MavensMate project from an existing non-MavensMate Force.com project, open the project directory in your MavensMate-enabled IDE/editor, right click the project name in the sidebar and select "Create MavensMate Project"')
        
        if action == 'existing':
            if not os.path.isdir(os.path.join(self.directory,"src")):
                raise MMException('Could not find "src" directory in project root.')
            if not os.path.isfile(os.path.join(self.directory,"src","package.xml")):
                raise MMException('Could not find package.xml in project src directory.')
            existing_parent_directory = os.path.dirname(self.directory)
            existing_is_in_workspace = True
            if existing_parent_directory != config.connection.workspace:
                existing_is_in_workspace = False
            if os.path.isdir(os.path.join(config.connection.workspace,self.project_name)) and existing_is_in_workspace == False and action == 'existing':
                raise MMException("A project with this name already exists in your workspace.")   

        self.sfdc_client = MavensMateClient(credentials={"username":self.username,"password":self.password,"org_type":self.org_type,"org_url":self.org_url})             
        self.id = util.new_mavensmate_id()
        if action == 'new':
            project_metadata = self.sfdc_client.retrieve(package=self.package)
            debug(project_metadata)
            debug('<-------->')
            util.put_project_directory_on_disk(self.project_name, force=True)
            util.extract_base64_encoded_zip(project_metadata.zipFile, os.path.join(config.connection.workspace,self.project_name))
            util.rename_directory(os.path.join(config.connection.workspace,self.project_name,"unpackaged"), os.path.join(config.connection.workspace,self.project_name,"src"))
        elif action == 'existing' and existing_is_in_workspace == False:
            shutil.move(self.directory, config.connection.workspace)

        self.location = os.path.join(config.connection.workspace,self.project_name)
        self.__put_project_file()
        self.__put_project_settings_file()
        self.__put_base_config()
        self.__set_sfdc_session()

        if action != 'new':
            project_metadata = self.sfdc_client.retrieve(package=os.path.join(config.connection.workspace,self.project_name,"src","package.xml"))
        
        self.conflict_manager = ConflictManager(self)
        self.conflict_manager.init_local_store(project_metadata)

        if config.connection.get_plugin_client_setting("mm_mass_index_apex_symbols", False):
            self.index_apex_symbols() #todo: daemon??

        util.put_password_by_key(self.id, self.password)
        self.sfdc_session = self.__get_sfdc_session() #hacky...need to fix
        
        if os.path.exists(os.path.join(config.connection.workspace,self.project_name,"metadata.zip")):
            os.remove(os.path.join(config.connection.workspace,self.project_name,"metadata.zip"))

        if action == 'new':
            return util.generate_success_response("Project Retrieved and Created Successfully")
        else:
            return util.generate_success_response("Project Created Successfully")
       
    def compile(self, params):
        tmp = util.put_tmp_directory_on_disk()
        shutil.copytree(os.path.join(config.project.location,"src"), os.path.join(tmp,"src"))
        util.rename_directory(os.path.join(tmp,"src"), os.path.join(tmp,"unpackaged"))
        zip_file = util.zip_directory(tmp, tmp)
        mm_compile_rollback_on_error = config.connection.get_plugin_client_setting("mm_compile_rollback_on_error", False)
        deploy_params = {
            "zip_file"          : zip_file,
            "rollback_on_error" : mm_compile_rollback_on_error,
            "ret_xml"           : True
        }
        deploy_result = config.sfdc_client.deploy(deploy_params)
        d = xmltodict.parse(deploy_result,postprocessor=util.xmltodict_postprocessor)

        dictionary = collections.OrderedDict()
        dictionary2 = []

        result = d["soapenv:Envelope"]["soapenv:Body"]['checkDeployStatusResponse']['result']
        
        for x, y in result.iteritems():
            if(x == "id"):
                dictionary["id"] = y
            if(x == "runTestResult"):
                dictionary["runTestResult"] = y
            if(x == "success"):
                dictionary["success"] = y

        if 'messages' in result:
            for a in result['messages']:
                for key, value in a.iteritems():
                    if(key == 'problemType' and value == 'Error'):
                        dictionary2.append(a)
        elif 'details' in result and result['details'] != None and 'componentFailures' in result['details']:
            if type(result['details']['componentFailures']) is not list:
                result['details']['componentFailures'] = [result['details']['componentFailures']]
            for a in result['details']['componentFailures']:
                dictionary2.append(a)

        dictionary["Messages"] = dictionary2 

        shutil.rmtree(tmp)

        config.project.conflict_manager.refresh_local_store(directories=[os.path.join(config.project.location, 'src')])

        return json.dumps(dictionary, sort_keys=True, indent=2, separators=(',', ': '))
        #return json.dumps(d["soapenv:Envelope"]["soapenv:Body"]['checkDeployStatusResponse']['result'], sort_keys=True, indent=2, separators=(',', ': '))
    

    #updates the salesforce.com credentials associated with the project
    def update_credentials(self, params):
        username = params.get('username', None)
        password = params.get('password', None)
        org_type = params.get('org_type', None)
        org_url  = params.get('org_url', None)

        if username == None or password == None:
            raise MMException('Please provide username and password')

        if org_type == None:
            raise MMException('Please provide an org_type (developer, production, sandbox, prerelease)')

        self.sfdc_client = MavensMateClient(credentials={"username":username,"password":password,"org_type":org_type,"org_url":org_url}, override_session=True)              
        
        if int(float(util.SFDC_API_VERSION)) >= 27:
            self.reset_metadata_container()

        self.username = params['username']
        self.password = params['password']
        self.org_type = params['org_type']
        self.environment = self.org_type
        self.org_url  = params.get('org_url', None)
        self.id = self.settings['id']

        util.put_password_by_key(self.id, self.password)
        self.__put_base_config()
        self.__set_sfdc_session()

    #upgrades project from the legacy format to 2.0+format
    def upgrade(self):
        self.sfdc_client = MavensMateClient(credentials={"username":self.username,"password":self.password,"org_type":self.org_type})             
        self.id = util.new_mavensmate_id()
        self.__put_project_file()
        self.__put_project_settings_file()
        self.__put_base_config()
        self.__set_sfdc_session()
        if config.connection.get_plugin_client_setting("mm_mass_index_apex_symbols", False):
            self.index_apex_symbols()
        if not os.path.exists(os.path.join(self.location,"config",".local_store")):
            if self.conflict_manager == None:
                self.conflict_manager = ConflictManager(self)
            project_metadata = self.sfdc_client.retrieve(package=os.path.join(self.location,"src","package.xml"))
            self.conflict_manager.init_local_store(project_metadata)
        util.put_password_by_key(self.id, self.password)
        self.sfdc_session = self.__get_sfdc_session() #hacky...need to fix
        if os.path.exists(os.path.join(self.location,"config","settings.yaml")):
            os.remove(os.path.join(self.location,"config","settings.yaml"))
        if os.path.exists(os.path.join(self.location,"config",".apex_file_properties")):
            os.remove(os.path.join(self.location,"config",".apex_file_properties"))
        return util.generate_success_response("Project Upgraded Successfully")

    def update_package_xml_with_metadata(self, metadata_type, api_name, operation='insert'):
        supported_types = ['ApexClass', 'ApexTrigger', 'ApexComponent', 'ApexPage']
        if metadata_type not in supported_types:
            return
        package_types = self.get_package_types()
        for i, val in enumerate(package_types):
            if val['name'] == metadata_type:
                if val['members'] == '*':
                    pass #we don't need to add/remove here
                else:
                    if operation == 'insert' and api_name not in val['members']:
                        if type(val['members']) is not list:
                            val['members'] = [val['members']]
                        val['members'].append(api_name)
                        val['members'] = sorted(val['members'])
                    elif operation == 'delete' and api_name in val['members']:
                        if type(val['members']) is not list:
                            val['members'] = [val['members']]
                        val['members'].pop(api_name)
                        if type(val['members']) is list:
                            val['members'] = sorted(val['members'])
                        else:
                            val['members'] = ""

        metadata_hash = collections.OrderedDict()
        for val in package_types:
            if val['members'] == "*" or type(val['members']) is list:
                metadata_hash[val['name']] = val['members']
            else:
                metadata_hash[val['name']] = [val['members']]

        new_package_xml_contents = util.get_package_xml_contents(metadata_hash)
        existing_package_xml = open(os.path.join(self.location,"src","package.xml"), "w")
        existing_package_xml.write(new_package_xml_contents)
        existing_package_xml.close()

    def run_health_check(self):
        return HealthCheck(self.location).run()

    def open_file_in_client(self, payload):
        file_name = payload["file_name"]
        extension = util.get_file_extension_no_period(file_name)
        mtype = util.get_meta_type_by_suffix(extension)
        full_file_path = os.path.join(self.location, "src", mtype["directoryName"], file_name)
        params = {
            "project_name"  : self.project_name,
            "file_name"     : full_file_path,
            "line_number"   : payload.get("line_number", 0)
        } 
        config.connection.run_subl_command("open_file_in_project", json.dumps(params))
        return util.generate_success_response("ok")

    def sync_with_server(self, params):
        pass

    def update_subscription(self, params):
        current_settings = self.__get_settings()
        new_sub = params['subscription']
        if type(new_sub) is not list:
            new_sub = [new_sub]
        current_settings['subscription'] = new_sub
        self.put_settings_file(current_settings)
        return util.generate_success_response('Subscription updated successfully')

    def reset_metadata_container(self, **kwargs):
        self.sfdc_client.delete_mavensmate_metadatacontainers_for_this_user()
        resp = self.sfdc_client.new_metadatacontainer_for_this_user()
        new_settings = self.settings
        new_settings['metadata_container'] = resp["id"]
        self.put_settings_file(new_settings)
        accept = kwargs.get("accept", None)
        if accept == None:
            return resp["id"]
        else:
            return util.generate_success_response('Operation completed successfully')

    #reverts a project to the server state based on the existing package.xml
    def clean(self, **kwargs):
        try:
            if self.sfdc_client == None or self.sfdc_client.is_connection_alive() == False:
                self.sfdc_client = MavensMateClient(credentials=self.get_creds(), override_session=True)  
                self.__set_sfdc_session()
            
            self.package = kwargs.get('package', self.package)

            #TESTING: moving to tmp directory in case something goes wrong during clean
            # tmp = util.put_tmp_directory_on_disk()
            # shutil.copytree(self.location, tmp)
            if kwargs.get('reset_metadata_container', False):
                use_tooling_api = config.connection.get_plugin_client_setting('mm_compile_with_tooling_api', False)
                if use_tooling_api == True and int(float(util.SFDC_API_VERSION)) >= 27:
                    self.reset_metadata_container()

            try:
                project_metadata = self.sfdc_client.retrieve(package=self.package)
            except xml.parsers.expat.ExpatError, e:
                raise MMException('Malformed package.xml: '+e.message)

            #freshen local store
            self.conflict_manager.refresh_local_store(project_metadata.fileProperties)
            
            util.extract_base64_encoded_zip(project_metadata.zipFile, self.location)

            #removes all metadata from directories
            for dirname, dirnames, filenames in os.walk(os.path.join(self.location,"src")):
                if '.git' in dirnames:
                    dirnames.remove('.git')
                if '.svn' in dirnames:
                    dirnames.remove('.svn')

                for filename in filenames:
                    full_file_path = os.path.join(dirname, filename)
                    if config.is_windows:
                        if '\\src\\package.xml' not in full_file_path:
                            os.remove(full_file_path)
                    else:
                        if '/src/package.xml' not in full_file_path:
                            os.remove(full_file_path)

            #replaces with retrieved metadata
            for dirname, dirnames, filenames in os.walk(os.path.join(self.location,"unpackaged")):
                for filename in filenames:
                    full_file_path = os.path.join(dirname, filename)
                    if config.is_windows:
                        if '\\unpackaged\\package.xml' in full_file_path:
                            continue
                    else:
                        if '/unpackaged/package.xml' in full_file_path:
                            continue
                    if config.is_windows:
                        destination = full_file_path.replace('\\unpackaged\\', '\\src\\')
                    else:
                        destination = full_file_path.replace('/unpackaged/', '/src/')
                    destination_directory = os.path.dirname(destination)
                    if not os.path.exists(destination_directory):
                        os.makedirs(destination_directory)
                    shutil.move(full_file_path, destination)
           
            #remove empty directories
            for dirname, dirnames, filenames in os.walk(os.path.join(self.location,"src")):
                if dirname == os.path.join(self.location,"src"):
                    continue
                if os.path.dirname(dirname) != os.path.join(self.location,"src"):
                    if util.is_directory_empty(dirname):
                        shutil.rmtree(dirname)

            for dirname, dirnames, filenames in os.walk(os.path.join(self.location,"src")):
                if dirname == os.path.join(self.location,"src"):
                    continue
                if os.path.dirname(dirname) == os.path.join(self.location,"src"):
                    if util.is_directory_empty(dirname):
                        shutil.rmtree(dirname)
                    

            if 'overwrite_package_xml' in kwargs and kwargs['overwrite_package_xml'] == True:
                os.remove(os.path.join(self.location,"src","package.xml"))
                shutil.move(os.path.join(self.location,"unpackaged","package.xml"), os.path.join(self.location,"src"))
            shutil.rmtree(os.path.join(self.location,"unpackaged"))
            if config.is_windows:
                os.remove(os.path.join(self.location,"metadata.zip"))
            return util.generate_success_response('Project Cleaned Successfully')
        except Exception, e:
            #TODO: if the clean fails, we need to have a way to ensure the project is returned to its original state
            #maybe we copy the project tree to a tmp folder, if we encounter an exception, we can remove the project
            #and replace it with the copied one in tmp
            #raise e
            return util.generate_error_response(e.message)

    def get_retrieve_result(self, params):
        if 'directories' in params and len(params['directories']) > 0 and 'files' in params and len(params['files']) > 0:
            raise MMException("Please select either directories or files to refresh, not both")
        elif 'directories' in params and len(params['directories']) > 0:
            metadata = {}
            types = []
            for d in params['directories']:
                basename = os.path.basename(d)
                # refresh all if it's the project base or src directory
                if basename == config.project.project_name or basename == "src":
                    data = util.get_default_metadata_data()
                    if type(data) is dict and 'metadataObjects' in data:
                        data = data['metadataObjects']
                    for item in data: 
                        if 'directoryName' in item:
                            types.append(item['xmlName'])
                else:
                    metadata_type = util.get_meta_type_by_dir(basename)
                    if metadata_type:
                        types.append(metadata_type['xmlName'])
                        if 'childXmlNames' in metadata_type:
                            for child in metadata_type['childXmlNames']:
                                types.append(child)
          
            custom_fields = []
            for val in self.get_package_types():
                package_type = val['name']
                members = val['members']
                if package_type not in types:
                    continue;

                metadata[package_type] = members

                if package_type == 'CustomObject':
                    for member in members:
                        if members == "*":
                            for item in self.get_org_metadata():
                               if item['xmlName'] == 'CustomObject':
                                    for child in item['children']:
                                        if not child['title'].endswith("__c"):
                                            for props in child['children']:
                                                if props['title'] == 'fields':
                                                    for field in props['children']:
                                                        custom_fields.append(child['title']+'.'+field['title'])
                                                    break
                                            if member != "*":
                                                break
                                    break

                    if len(custom_fields):
                        if 'CustomField' not in metadata:
                            metadata['CustomField'] = []
                        metadata['CustomField'] = list(set(metadata['CustomField']+custom_fields))

            if len(metadata) == 0:
                raise MMException("Could not find metadata types to refresh")
        elif 'files' in params and len(params['files']) > 0:
            metadata = util.get_metadata_hash(params['files'])
        else:
            raise MMException("Please provide either an array of 'directories' or an array of 'files'")

        #retrieves a fresh set of metadata based on the files that have been requested
        retrieve_result = self.sfdc_client.retrieve(package=metadata)
        return retrieve_result

    def index_apex_symbols(self, apex_class_name_or_names=None):
        '''
            Writes out symbol tables to project's config/.symbols directory
        '''
        
        try:
            if not os.path.exists(os.path.join(self.location,"config",".symbols")):
                os.makedirs(os.path.join(self.location,"config",".symbols"))
            
            symbol_table_result = {
                "records" : []
            }

            if apex_class_name_or_names == None:
                apex_ids = []
                classes = self.sfdc_client.list_metadata("ApexClass", True)
                for c in classes:
                    apex_ids.append(c['id'])

                list_of_apex_id_lists = list(util.list_grouper(20, apex_ids)) #split apex ids into lists of max size 20
                for apex_ids_list in list_of_apex_id_lists:                    
                    local_symbol_table_result = self.sfdc_client.get_symbol_tables_by_class_id(apex_ids_list)
                    if 'records' in local_symbol_table_result and len(local_symbol_table_result['records']) > 0:
                        symbol_table_result['records'] = symbol_table_result['records'] + local_symbol_table_result['records']
            else:
                class_names = []
                if type(apex_class_name_or_names) is not list:
                    apex_class_name_or_names = [apex_class_name_or_names]

                for class_name in apex_class_name_or_names:
                    apex_class_name = os.path.basename(class_name)
                    apex_class_name = apex_class_name.replace(".cls","")
                    class_names.append(apex_class_name)

                list_of_apex_class_name_lists = list(util.list_grouper(20, class_names)) #split apex ids into lists of max size 20
                for apex_class_names_list in list_of_apex_class_name_lists:                    
                    local_symbol_table_result = self.sfdc_client.get_symbol_tables_by_class_name(apex_class_names_list)
                    if 'records' in local_symbol_table_result and len(local_symbol_table_result['records']) > 0:
                        symbol_table_result['records'] = symbol_table_result['records'] + local_symbol_table_result['records']

            if 'records' in symbol_table_result and len(symbol_table_result['records']) > 0:
                for r in symbol_table_result['records']:
                    if "SymbolTable" in r and r["SymbolTable"] != None and r["SymbolTable"] != {}:
                        file_name = ""
                        if "NamespacePrefix" in r and r["NamespacePrefix"] != None:
                            file_name = r["NamespacePrefix"]+"."+r["Name"]+".json"
                        else:
                            file_name = r["Name"]+".json"
                        src = open(os.path.join(self.location,"config",".symbols",file_name), "w")
                        json_data = json.dumps(r["SymbolTable"], indent=4)
                        src.write(json_data)
                        src.close()

            return util.generate_success_response("Apex symbols indexed successfully")
        #except (TypeError):
        except BaseException, e:
            debug('------> error indexing apex symbols')
            debug(e.message)

            directories = []
            if os.path.exists(os.path.join(self.location, 'src', 'classes')):
                directories.append(os.path.join(self.location, 'src', 'classes'))

            if os.path.exists(os.path.join(self.location, 'src', 'triggers')):
                directories.append(os.path.join(self.location, 'src', 'triggers'))

            params = {
                'files'         : [],
                'directories'   : directories
            }
            retrieve_result = self.get_retrieve_result(params)
            fileProperties = retrieve_result.fileProperties
            apex_ids = []
            for prop in fileProperties:
                if prop.type == "ApexClass":
                    apex_ids.append(prop.id)   
            symbol_table_result = self.sfdc_client.get_symbol_table(apex_ids)
            debug(symbol_table_result)
            if 'records' in symbol_table_result and len(symbol_table_result['records']) > 0:
                for r in symbol_table_result['records']:
                    if "SymbolTable" in r and r["SymbolTable"] != None and r["SymbolTable"] != {}:
                        file_name = ""
                        if "NamespacePrefix" in r and r["NamespacePrefix"] != None:
                            file_name = r["NamespacePrefix"]+"."+r["Name"]+".json"
                        else:
                            file_name = r["ContentEntity"]["Name"]+".json"
                        src = open(os.path.join(self.location,"config",".symbols",file_name), "w")
                        json_data = json.dumps(r["SymbolTable"], indent=4)
                        src.write(json_data)
                        src.close()

            return util.generate_success_response("Apex symbols indexed successfully")
        
    # def refresh_index(self, mtypes=[]):
    #     mm_metadata.index_metadata(mtypes)

    def select_metadata_based_on_package_xml(self, return_list, package_location='project'):
        #process package and select only the items the package has specified
        debug(package_location)
        if package_location == 'project' or package_location == 'package.xml':
            package_types = self.get_package_types();
        else:
            package_types = self.get_package_types(package_location);
        #expand standard "custombjects" to customfields
        custom_fields = []
        for val in package_types:
            metadata_type = val['name']

            # If CustomObject is set in package.xml, look at it's members
            if metadata_type == 'CustomObject' and 'members' in val:
                for member in val['members']:
                    # Standard objects don't end with __c, or it's everything
                    if not member.endswith("__c") or member == "*":
                        # We need to look up the fields for this standard object in the org metadata
                        for item in return_list:
                            # CustomField is a child of CustomObject
                            if item['xmlName'] == 'CustomObject':
                                # Loop through all the CustomObject metadata
                                for child in item['children']:
                                    # Currently the standard object from the loop or everything
                                    if child['title'] == member or member == "*":
                                        for props in child['children']:
                                            for field in props['children']:
                                                custom_fields.append(child['title']+'.'+field['title'])
                                        # we can break unless we want to add every field to CustomField for *
                                        if member != "*":
                                            break
                                # we only need to look at CustomObject
                                break

        if len(custom_fields) > 0:
            custom_field = None
            new_packages = []
            for val in package_types:
                if val['name'] == 'CustomField':
                    custom_field = val
                else:
                    new_packages.append(val)

            if custom_field == None:
                custom_field = {'name':'CustomField'}

            if 'members' in custom_field and type(custom_field['members']) == list:
                members = custom_field['members']
            else:
                members = []
            custom_field['members'] = list(set(members+custom_fields))
            new_packages.append(custom_field)
            package_types = new_packages

        for val in package_types:
            metadata_type = val['name']
            metadata_def = util.get_meta_type_by_name(metadata_type)

            #print('processing --> ', metadata_type)

            if metadata_def == None:
                continue
            
            members = val['members']
            #print 'processing: ', metadata_type
            #print 'package members: ', members
            
            is_parent_type  = 'parentXmlName' not in metadata_def
            is_child_type   = 'parentXmlName' in metadata_def
            is_folder_based = 'inFolder' in metadata_def and metadata_def['inFolder'] == True
            
            server_metadata_item = None
            
            #print('is_parent_type --> ', is_parent_type)
            #print('is_child_type --> ', is_child_type)
            #print('is_folder_based --> ', is_folder_based)

            #loop through list of metadata types in the org itself,
            #try to match on the name of this type of metadata
            for item in return_list:
                if is_parent_type and item['xmlName'] == metadata_type:
                    server_metadata_item = item
                    break
                if is_child_type and item['xmlName'] == metadata_def['parentXmlName']:
                    server_metadata_item = item
                    break

            if server_metadata_item == None:
                continue

            if members == "*": #if package is subscribed to all
                server_metadata_item['select'] = True
                if 'children' in server_metadata_item:
                    for child in server_metadata_item['children']:
                        child['select'] = True
                        if 'children' in child:
                            for gchild in child['children']:
                                gchild['select'] = True
                                if 'children' in gchild:
                                    for ggchild in gchild['children']:
                                        ggchild['select'] = True
                continue
            else: #package has specified members (members => ['Account', 'Lead'])
            
                if type(members) is not list:
                    members = [members]
                
                if is_folder_based: #e.g.: dashboard, report, etc.
                    #print 'folder based!'
                    for m in members:
                        if '/' in m:
                            arr = m.split("/")
                            folder_name = arr[0]
                            item_name = arr[1]
                        else:
                            folder_name = m

                        if '/' in m: #it doesnt seem to matter to set the folder as selected?
                            for child in server_metadata_item['children']:
                                if child['title'] == folder_name:
                                    for folder_item in child['children']:
                                        if folder_item['title'] == item_name:
                                            folder_item['select'] = True
                                            break
                                    break

                elif is_child_type: #weblink, customfield, etc.
                    #print('handling child! --> ')
                    #print('members --> ', members)

                    #print 'child type!'
                    parent_type = util.get_meta_type_by_name(metadata_def['parentXmlName'])
                    for item in return_list:
                        if item['xmlName'] == parent_type['xmlName']:
                            parent_server_metadata_item = item

                    for m in members: #members => [Contact.FieldA, Contact.FieldB, etc.]
                        arr = m.split(".")
                        object_name = arr[0]
                        item_name = arr[1]
                        for child in parent_server_metadata_item['children']:
                            #print 'child: ', child
                            if child['title'] == object_name:
                                #"Account"
                                for gchild in child['children']:
                                    #print 'gchild: ', gchild
                                    #"fields"
                                    for ggchild in gchild['children']:
                                        #print 'ggchild: ', ggchild
                                        if gchild['title'] == metadata_def['tagName'] and ggchild['title'] == item_name:
                                            #print 'selecting: ', ggchild
                                            #"field_name__c"
                                            ggchild['select'] = True
                                        #break
                                #break

                else:
                    #print 'regular type with specific items selected'
                    if item['xmlName'] == 'CustomObject':
                        selected = 0
                    for m in members:
                        for child in server_metadata_item['children']:
                            if child['title'] == m:
                                child['select'] = True
                                if item['xmlName'] == 'CustomObject':
                                    selected += 1
                                if 'children' in child:
                                    for gchild in child['children']:
                                        gchild['select'] = True
                                        for ggchild in gchild['children']:
                                            ggchild['select'] = True
                    if item['xmlName'] == 'CustomObject' and selected == len(server_metadata_item['children']):
                        item['select'] = True
        
        return return_list

    def __get_package_as_dict(self, location='project'):
        debug(location)
        if location == 'project':
            return util.parse_xml_from_file(os.path.join(self.location,"src","package.xml"))
        else:
            return util.parse_xml_from_file(location)

    def get_package_types(self, package_location="project"):
        debug('get_package_types')
        debug(package_location)
        try:
            if package_location == 'project':
                pkg = self.__get_package_as_dict()
            else:
                pkg = self.__get_package_as_dict(package_location)
            package_types = pkg['Package']['types']
            if not isinstance(package_types, (list, tuple)):
                package_types = [package_types]
            return package_types
        except:
            return []

    def get_is_metadata_indexed(self):
        try:
            if os.path.exists(os.path.join(self.location,"config",".org_metadata")):
                json_data = util.parse_json_from_file(os.path.join(self.location,"config",".org_metadata"))
                return True
            else:
                return False
        except:
            return False

    def get_org_users_list(self):
        if self.sfdc_client == None or self.sfdc_client.is_connection_alive() == False:
            self.sfdc_client = MavensMateClient(credentials=self.get_creds(), override_session=False)  
            self.__set_sfdc_session()
        try:
            query_result = self.sfdc_client.execute_query('Select Id, Name From User Where IsActive = True order by Name limit 10000')
        except:
            query_result = self.sfdc_client.execute_query('Select Id, Name From User Where Active = True order by Name limit 10000')
        if 'records' in query_result:
            return query_result['records']
        else:
            return []

    def filter_indexed_metadata(self, payload):
        om = self.get_org_metadata(False, False, payload.get("ids", []), payload.get("keyword", None))
        return json.dumps(om)

    def index_metadata(self, mtypes=None):
        sfdc_client = config.sfdc_client
        return_list = []
        if sfdc_client == None or sfdc_client.is_connection_alive() == False:
            sfdc_client = MavensMateClient(credentials=self.get_creds(), override_session=True)  
            self.set_sfdc_session()

        data = self.get_org_describe()
        threads = []
        thread_results = []
        creds = self.get_creds()

        to_be_indexed = []

        if mtypes != None:
            if type(mtypes) is not list:
                mtypes = [mtypes]
            for mt in mtypes:
                for md in data:
                    if md['xmlName'] == mt:
                        to_be_indexed.append(md)
                        break
        else:
            to_be_indexed = data

        metadata_chunks = list(util.grouper(8, to_be_indexed))
        for chunk in metadata_chunks:                    
            thread_client = MavensMateClient(credentials=creds)
            thread = IndexCall(thread_client, chunk)
            threads.append(thread)
            thread.start()
            
        for thread in threads:
            thread.join()
            if len(thread.results) == len(thread.clean_types):
                thread_results.extend(thread.results)
        
        return_list = sorted(thread_results, key=itemgetter('text')) 

        #no specific metadata types were requested, 
        #so we simply overwirte .org_metadata with the new index 
        if mtypes == None:
            file_body = json.dumps(return_list, sort_keys=False, indent=4)
            src = open(os.path.join(self.location,"config",".org_metadata"), "w")
            src.write(file_body)
            src.close()
            #return file_body
        #specific metadata types were requested, so update .org_metadata with the result
        elif type(return_list) is list and len(return_list) > 0:
            existing_index = self.get_org_metadata()
            for mt in return_list:
                for emt in existing_index:
                    if emt['xmlName'] == mt['xmlName']:
                        emt['children'] = mt['children']
                        break

            file_body = json.dumps(existing_index, sort_keys=False, indent=4)
            src = open(os.path.join(self.location,"config",".org_metadata"), "w")
            src.write(file_body)
            src.close()
        return util.generate_success_response("Org indexed successfully")

    def get_org_metadata(self, raw=False, selectBasedOnPackageXml=False, selectedIds=[], keyword=None, **kwargs):
        if self.get_is_metadata_indexed():
            if raw:
                org_metadata_raw = util.get_file_as_string(os.path.join(self.location,"config",".org_metadata"))
                org_index = json.loads(org_metadata_raw)
                if selectBasedOnPackageXml:
                    self.select_metadata_based_on_package_xml(org_index)
                elif len(selectedIds) > 0 or keyword != None:
                    if keyword != None:
                        crawlJson.setVisibility(org_index, keyword)
                    if len(selectedIds) > 0:
                        crawlJson.setChecked(org_index, selectedIds)
                return json.dumps(org_index)
            else:
                org_index = util.parse_json_from_file(os.path.join(self.location,"config",".org_metadata"))
                if selectBasedOnPackageXml:
                    self.select_metadata_based_on_package_xml(org_index)
                elif len(selectedIds) > 0 or keyword != None:
                    if keyword != None:
                        crawlJson.setVisibility(org_index, keyword)
                    if len(selectedIds) > 0:
                        crawlJson.setChecked(org_index, selectedIds)
                return org_index
        else:
            self.index_metadata()
            org_index = util.parse_json_from_file(os.path.join(self.location,"config",".org_metadata"))
            self.select_metadata_based_on_package_xml(org_index)
            return org_index


    def __get_settings(self):
        #returns settings for this project
        try:
            if os.path.isfile(os.path.join(self.location,"config",".settings")):
                settings = util.parse_json_from_file(os.path.join(self.location,"config",".settings"))
                if settings == None:
                    raise MMException('Unable to read settings file for this project.')
                return settings
            else:
                return {}
        except:
            raise MMException('Unable to read settings file for this project.')

    def get_creds(self): 
        #initialize variables so it doesn't bomb if any are missing
        id, project_name, username, environment, endpoint, org_type, password, is_legacy = None, '', '', None, '', '', '', False
        #get the mm project settings
        settings = self.__get_settings()

        #get the common project properties
        if 'id' in settings: 
            id = settings['id']
        if 'project_name' in settings: 
            project_name = settings['project_name']
        else:
            #default to project folder name
            project_name = os.path.basename(self.location)
        if 'username' in settings: 
            username = settings['username']
        if 'environment' in settings: 
            #TODO: let's standardize environment vs. org_type (org_type is preferred)
            environment, org_type = settings['environment'], settings['environment']
            if 'org_url' in settings and settings['org_url'] != None and settings['org_url'] != '':
                endpoint = util.get_soap_url_from_custom_url(settings['org_url'])
            else:
                endpoint = util.get_sfdc_endpoint_by_type(environment)
        #get password from id, or name for legacy/backup
        if id:
            password = util.get_password_by_key(id)
        
        if password == None:
            raise MMException("Unable to retrieve password from the keychain store.")

        creds = { }
        creds['username'] = username
        creds['password'] = password
        creds['endpoint'] = endpoint
        creds['org_type'] = org_type
        creds['org_url']  = settings.get('org_url', None)
        if self.sfdc_session != None:
            creds['user_id']                = self.sfdc_session.get('user_id', None)
            creds['sid']                    = self.sfdc_session.get('sid', None)
            creds['metadata_server_url']    = self.sfdc_session.get('metadata_server_url', None)
            creds['endpoint']               = self.sfdc_session.get('endpoint', None)
            creds['server_url']             = self.sfdc_session.get('server_url', None)
        return creds


    def log_anonymous_apex(self, apex_body, log, script_name=None):
        if not os.path.exists(os.path.join(self.location, "apex-scripts", "log")):
            os.makedirs(os.path.join(self.location, "apex-scripts", "log"))
        location = os.path.join(self.location, "apex-scripts", "log", util.get_timestamp().replace(":",".")+".log")
        src = open(location, "w")
        file_body = ""
        if script_name != None:
            file_body += script_name
        else:
            file_body += "Execute Anonymous"
        file_body += "\n\n"
        file_body += "================================"
        file_body += "\n\n"
        file_body += apex_body
        file_body += "\n\n"
        file_body += "================================"
        file_body += "\n\n"
        file_body += log
        src.write(file_body.encode('utf-8').strip())
        src.close()
        return location

    def update_setting(self, setting, value):
        self.settings[setting] = value
        self.put_settings_file(self.settings)

    #write a file containing the MavensMate settings for the project
    def put_settings_file(self, settings=None):
        if settings == None:
            settings = {
                "project_name"          : self.project_name,
                "workspace"             : config.connection.workspace,
                "username"              : self.username,
                "environment"           : self.org_type,
                "namespace"             : self.sfdc_client.get_org_namespace(),
                "id"                    : self.id,
                "org_url"               : self.org_url,
                "subscription"          : self.subscription or config.connection.get_plugin_client_setting('mm_default_subscription')
            }

            if int(float(util.SFDC_API_VERSION)) >= 27:
                settings['metadata_container'] = self.sfdc_client.get_metadata_container_id()
        src = open(os.path.join(config.connection.workspace,self.project_name,"config",".settings"), "w")
        json_data = json.dumps(settings, sort_keys=False, indent=4)
        src.write(json_data)
        src.close()

    #write a file containing the dynamic describe information for the org
    def __put_describe_file(self):
        file_name = ".describe"
        src = open(os.path.join(config.connection.workspace,self.project_name,"config",file_name), "w")
        describe_result = self.sfdc_client.describeMetadata()
        d = xmltodict.parse(describe_result,postprocessor=util.xmltodict_postprocessor)
        json_data = json.dumps(d["soapenv:Envelope"]["soapenv:Body"]["describeMetadataResponse"]["result"], sort_keys=True, indent=4)
        src.write(json_data)
        src.close()

    #write a file containing the dynamic describe information for the org
    def put_overlays_file(self, overlays):
        file_name = ".overlays"
        src = open(os.path.join(config.connection.workspace,self.project_name,"config",file_name), "w")
        src.write(overlays)
        src.close()   

    def get_org_connections(self):
        try:
            if not os.path.exists(os.path.join(self.location,"config",".org_connections")):
                return []
            return util.parse_json_from_file(os.path.join(self.location,"config",".org_connections"))
        except:
            return []

    #returns a list of all deployment names
    def get_deployments(self):
        package_names = []
        package_names.append({
            'label' : 'package.xml',
            'location' : 'package.xml'
        })
        try:
            if not os.path.isfile(os.path.join(self.location,"deploy",".config")):
                return package_names
            else:
                deploy_config_file = util.parse_json_from_file(os.path.join(self.location,"deploy",".config"))
                named_deployments = deploy_config_file['deployments']['named']
                for nd in named_deployments:
                    package_names.append({
                        'label' : nd['name'] + ' ['+nd['timestamp']+'] ('+nd['destination']+')',
                        'location' : nd['package']
                    })

                timestamped_deployments = deploy_config_file['deployments']['timestamped']
                for td in timestamped_deployments:
                    package_names.append({
                        'label' : td['timestamp'] + ' ('+td['destination']+')',
                        'location' : td['package']
                    })
        except:
            return package_names
        return package_names

    #returns metadata types for this org, or default types
    def get_org_describe(self):
        try:
            om = util.parse_json_from_file(os.path.join(self.location,"config",".describe"))
            mlist = []
            if self.subscription != None and type(self.subscription) is list and len(self.subscription) > 0:
                for m in om['metadataObjects']:
                    if m['xmlName'] in self.subscription:
                        mlist.append(m)
            return mlist
        except:
            om = util.get_default_metadata_data()
            mlist = []
            if self.subscription != None and self.subscription is list and len(self.subscription) > 0:
                for m in om['metadataObjects']:
                    if m['xmlName'] in self.subscription:
                        mlist.append(m)
            return mlist

    def __put_base_config(self):
        if os.path.isdir(os.path.join(config.connection.workspace,self.project_name,"config")) == False:
            os.makedirs(os.path.join(config.connection.workspace,self.project_name,"config"))
        self.put_settings_file()
        self.__put_describe_file()
        self.put_debug_file()

    def put_debug_file(self, users=None, levels=None, expiration=480):
        project_path = os.path.join(config.connection.workspace,self.project_name)
        if not os.path.exists(os.path.join(project_path, 'config')):
            os.makedirs(os.path.join(project_path, 'config'))
        
        #put .debug
        src = open(os.path.join(project_path, 'config', '.debug'), "w")  
        debug_settings = {}
        default_levels = {
            "Database"      : "INFO",
            "System"        : "DEBUG",
            "Visualforce"   : "INFO",
            "Workflow"      : "INFO",
            "Validation"    : "INFO",
            "Callout"       : "INFO",
            "ApexCode"      : "DEBUG"
        }
        debug_settings["users"]       = users or [self.sfdc_client.user_id]
        debug_settings["levels"]      = levels or default_levels
        debug_settings["expiration"]  = expiration
        src.write(json.dumps(debug_settings, sort_keys=False, indent=4))
        src.close()

        #put .apex_script
        src = open(os.path.join(project_path, 'config', '.apex_script'), "w")  
        debug_settings = {}
        default_levels = {
            "Db"                : "INFO",
            "Callout"           : "DEBUG",
            "Apex_profiling"    : "DEBUG",
            "Workflow"          : "INFO",
            "Validation"        : "INFO",
            "Callout"           : "INFO",
            "Apex_code"         : "DEBUG"
        }
        debug_settings["levels"] = default_levels
        src.write(json.dumps(debug_settings, sort_keys=False, indent=4))
        src.close()

    def __put_project_file(self):
        if config.connection.plugin_client == 'SUBLIME_TEXT_2' or config.connection.plugin_client == 'SUBLIME_TEXT_3':
            sublime_project_file_path = os.path.join(config.connection.workspace,self.project_name,self.project_name+".sublime-project")
            src = open(sublime_project_file_path, "w")
            project_file = {
                "folders" : [
                    { 
                        "path": ".",
                        "folder_exclude_patterns": ["config/.symbols"] 
                    }
                ],
                "settings" : {
                    "auto_complete_triggers" :
                    [
                        {
                            "selector": "source - comment",
                            "characters": "."
                        },
                        {
                            "selector": "text.html - comment", 
                            "characters": ":"
                        },
                        {
                            "selector": "text.html - comment", 
                            "characters": "<"
                        },
                        {
                            "selector": "text.html - comment", 
                            "characters": " "
                        }
                    ]
                }
            }
            src.write(json.dumps(project_file, sort_keys=False, indent=4))
            src.close()

    def __put_project_settings_file(self):
        #TODO: what about atom?
        if config.connection.plugin_client == 'SUBLIME_TEXT_2' or config.connection.plugin_client == 'SUBLIME_TEXT_3':
            body = [
                '/*',
                '',
                'MavensMate Project settings',
                'NOTE: MavensMate Project settings will override MavensMate default and user settings',
                '',
                '*/',
                '',
                '{',
                '   //"mm_api_version" : 29.0',
                '   //"mm_compile_with_tooling_api" : true',
                '}'
            ]
            path = os.path.join(config.connection.workspace,self.project_name,self.project_name+".sublime-settings")
            src = open(path, "w")
            src.write('\n'.join(body))
            src.close()

    def get_debug_users(self):
        users = []
        try:
            debug_settings = util.parse_json_from_file(os.path.join(self.location,"config",".debug"))
            users = debug_settings["users"]
        except:
            return ["{0}".format(self.sfdc_client.user_id)]
        return users

    #returns the cached session information
    def __get_sfdc_session(self):
        try:
            return util.parse_json_from_file(os.path.join(self.location,"config",".session"))
        except:
            return None

    def set_sfdc_session(self):
        self.__set_sfdc_session()

    #writes session information to the local cache
    def __set_sfdc_session(self):
        try:
            session = {
                "user_id"               : self.sfdc_client.user_id,
                "sid"                   : self.sfdc_client.sid,
                "metadata_server_url"   : self.sfdc_client.metadata_server_url,
                "server_url"            : self.sfdc_client.server_url,
                "endpoint"              : self.sfdc_client.endpoint
            }
            file_body = json.dumps(session)
            src = open(os.path.join(self.location,"config",".session"), "w")
            src.write(file_body)
            src.close()
        except:
            pass

    def get_debug_settings(self):
        try:
            debug_settings = util.parse_json_from_file(os.path.join(self.location,"config",".debug"))
            return debug_settings
        except:
            return None

class IndexCall(threading.Thread):
    def __init__(self, client, metadata_types):
        self.metadata_types = metadata_types
        self.client         = client
        self.results        = []
        self.clean_types    = []
        for mt in self.metadata_types:
            if mt != None:
                self.clean_types.append(mt)
        threading.Thread.__init__(self)

    def run(self):
        for mtype in self.clean_types:
            if mtype == None:
                self.results.append({})
                continue
            try:
                result = self.client.list_metadata(mtype['xmlName'])
                if result == None:
                    result = []
                self.results.append({
                    "title"         : mtype['xmlName'],
                    "text"          : mtype['xmlName'],
                    "xmlName"       : mtype['xmlName'],
                    "type"          : mtype,
                    "cls"           : "folder",
                    "expanded"      : False,
                    "children"      : result,
                    "checked"       : False,
                    "select"        : False,
                    "level"         : 1,
                    "id"            : mtype['xmlName'],
                    "key"           : mtype['xmlName'],
                    "isFolder"      : True,
                    "cls"           : "folder",
                    "inFolder"      : mtype['inFolder'],
                    "hasChildTypes" : 'childXmlNames' in mtype

                })
            except:
                self.results.append({
                    "title"         : mtype['xmlName'], 
                    "text"          : mtype['xmlName'],
                    "xmlName"       : mtype['xmlName'],
                    "type"          : mtype,
                    "cls"           : "folder",
                    "expanded"      : False,
                    "children"      : [],
                    "checked"       : False,
                    "select"        : False,
                    "level"         : 1,
                    "id"            : mtype['xmlName'],
                    "key"           : mtype['xmlName'],
                    "isFolder"      : True,
                    "cls"           : "folder",
                    "inFolder"      : mtype['inFolder'],
                    "hasChildTypes" : 'childXmlNames' in mtype
                })
                continue
