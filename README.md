mm
==

### IMPORTANT

The APIs in this project are deprecated. All development is currently occuring at https://github.com/joeferraro/MavensMate

##### master

[![Build Status](https://circleci.com/gh/joeferraro/mm.svg?style=shield&circle-token=0c3bafbd41995299906a7fc2a42205fcb8203509)](https://circleci.com/gh/joeferraro/mm)

### Overview

`mm` is an executable that powers MavensMate Force.com IDEs. You can use `mm` to perform every important task relative to developing on the Salesforce1 platform. For example, to compile a project:

```
$ mm compile_project
```

You can also use `mm` to provide a default UI for tasks like creating a new project, editing a project, running unit tests & anonymous apex, & deploying metadata to servers. Just use the --ui flag:

```
$ mm new_project --ui
```

In order to provide context to your operation, pipe json to `mm` via STDIN. For example:

```
$ mm compile_project <<< '{ "project_name" : "myproject" }'
```

### Installation

`mm` is a Python 2.7 package that can be installed and run traditionally (via Python) or optionally run as a standalone executable with no dependencies. 

#### As a Standalone Executable

- Download the appropriate GitHub release: [https://github.com/joeferraro/mm/releases](https://github.com/joeferraro/mm/releases)
- Ensure `mm` (or `mm.exe` on windows) in on your path
- Run a command: `$ mm new_project --ui`

#### As a Python Package

If you do not have Python 2.7 installed, you'll need to do so: [https://www.python.org/downloads/](https://www.python.org/downloads/).

##### pip

`pip` is the best way to install `mm`. To install `pip`: [http://pip.readthedocs.org/en/latest/installing.html](http://pip.readthedocs.org/en/latest/installing.html). Then run:

```
$ pip install mm
```

This will create an executable called `mm` (or `mm.exe` in Windows).

##### easy_install

```
$ easy_install mm
```

##### Manual

```
$ git clone https://github.com/joeferraro/mm.git
$ python setup.py install
```

### Running mm Commands

In order to run `mm` commands, it should be located on your path. For Linux/Unix users, this should be fairly straightforward. For Windows users: [http://stackoverflow.com/a/6318188/429814](http://stackoverflow.com/a/6318188/429814)

#### Examples:

##### Longhand

```
$ mm -o new_project -c SUBLIME_TEXT <<< '{"settings":{"mm_workspace":"some/location"}, "project_name" : "mycoolproject", "username":"foo@bar.com", "password":"foo", "org_type":"developer", "package": {"ApexClass":"*"}}'
```

##### Shorthand

```
$ mm new_project <<< '{"settings":{"mm_workspace":"some/location"}, "project_name" : "mycoolproject", "username":"foo@bar.com", "password":"foo", "org_type":"developer", "package": {"ApexClass":"*"}}'
```

### Command Line Arguments

<table>
  <tr>
    <th>Argument</th><th>Description</th>
  </tr>
  <tr>
    <td>-o</td><td>Requested Operation (optional)</td>
  </tr>
  <tr>
    <td>-c</td><td>Plugin client making the request ("Sublime Text" [default], "TextMate", "Notepad++", etc.)</td>
  </tr>
  <tr>
    <td>--ui</td><td>Launch the base UI for the operations</td>
  </tr>
</table>

### Supported Operations

All supported commands can be found here: <a href="https://github.com/joeferraro/mm/tree/master/lib/commands">https://github.com/joeferraro/mm/tree/master/lib/commands</a>

<table>
  <tr>
    <th>Operations</th><th>Description</th>
  </tr>
  <tr>
    <td>new_project</td><td>Creates a new project</td>
  </tr>
  <tr>
    <td>edit_project</td><td>Edits contents of a project</td>
  </tr>
  <tr>
    <td>upgrade_project</td><td>Upgrades a project</td>
  </tr>
  <tr>
    <td>compile_project</td><td>Compiles a project</td>
  </tr>
  <tr>
    <td>new_metadata</td><td>Creates new metadata</td>
  </tr>
  <tr>
    <td>refresh</td><td>Refreshes files and/or directories from the server</td>
  </tr>
  <tr>
    <td>clean_project</td><td>Reverts a project to server state based on package.xml</td>
  </tr>
  <tr>
    <td>compile</td><td>Compiles files and/or directories</td>
  </tr>
  <tr>
    <td>delete</td><td>Deletes metadata from the server</td>
  </tr>
  <tr>
    <td>get_active_session</td><td>Retrieves an active Salesforce.com session</td>
  </tr>
  <tr>
    <td>update_credentials</td><td>Updates the credentials associated with a project</td>
  </tr>
  <tr>
    <td>execute_apex</td><td>Executes a block of Apex</td>
  </tr>
  <tr>
    <td>deploy</td><td>Deploys metadata to one or more destination orgs</td>
  </tr>
  <tr>
    <td>test</td><td>Runs Apex unit tests</td>
  </tr>
  <tr>
    <td>list_metadata</td><td>Lists metadata of a certain type</td>
  </tr>
  <tr>
    <td>index_metadata</td><td>Indexes project metadata</td>
  </tr>
  <tr>
    <td>list_connections</td><td>List org connections for this project</td>
  </tr>
  <tr>
    <td>new_connection</td><td>Creates a new org connection</td>
  </tr>
  <tr>
    <td>delete_connection</td><td>Deletes an org connection</td>
  </tr>
  <tr>
    <td>index_apex_overlays</td><td>Indexes Apex checkpoints</td>
  </tr>
  <tr>
    <td>new_apex_overlay</td><td>Creates a new Apex checkpoint</td>
  </tr>
  <tr>
    <td>delete_apex_overlay</td><td>Deletes an Apex checkpoint</td>
  </tr>
  <tr>
    <td>fetch_logs</td><td>Fetches most recent Apex debug logs for this user</td>
  </tr>
  <tr>
    <td>fetch_checkpoints</td><td>Fetches most recent Apex checkpoints for this user</td>
  </tr>
  <tr>
    <td>new_project_from_existing_directory</td><td>Creates a new project from an existing directory</td>
  </tr>
  <tr>
    <td>open_sfdc_url</td><td>Opens metadata in Salesforce</td>
  </tr>
   <tr>
    <td>index_apex</td><td>Indexes Apex metadata for a project</td>
  </tr>
   <tr>
    <td>update_subscription</td><td>Updates metadata subscription for a project</td>
  </tr>
   <tr>
    <td>new_log</td><td>Creates a new Apex debug log</td>
  </tr>

</table>

