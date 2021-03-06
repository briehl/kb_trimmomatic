# -*- coding: utf-8 -*-
#BEGIN_HEADER
import sys
import traceback
from biokbase.workspace.client import Workspace as workspaceService
import requests
requests.packages.urllib3.disable_warnings()
import subprocess
import os
import re
from pprint import pprint, pformat
import uuid

## SDK Utils
from ReadsUtils.ReadsUtilsClient import ReadsUtils
from SetAPI.SetAPIServiceClient import SetAPI
from KBaseReport.KBaseReportClient import KBaseReport
#END_HEADER


class kb_trimmomatic:
    '''
    Module Name:
    kb_trimmomatic

    Module Description:
    A KBase module: kb_trimmomatic
This module contains two methods

runTrimmomatic() to backend a KBase App, potentially operating on ReadSets
execTrimmomatic() the local method that handles overloading Trimmomatic to run on a set or a single library
execTrimmomaticSingleLibrary() runs Trimmomatic on a single library
    '''

    ######## WARNING FOR GEVENT USERS ####### noqa
    # Since asynchronous IO can lead to methods - even the same method -
    # interrupting each other, you must be *very* careful when using global
    # state. A method could easily clobber the state set by another while
    # the latter method is running.
    ######################################### noqa
    VERSION = "1.0.0"
    GIT_URL = "https://github.com/kbaseapps/kb_trimmomatic"
    GIT_COMMIT_HASH = "4d3f9d3293eb02d21d2e6891b1c113bd64ad60f2"

    #BEGIN_CLASS_HEADER
    workspaceURL = None
    TRIMMOMATIC = 'java -jar /kb/module/Trimmomatic-0.36/trimmomatic-0.36.jar'
    ADAPTER_DIR = '/kb/module/Trimmomatic-0.36/adapters/'

    def log(self, target, message):
        if target is not None:
            target.append(message)
        print(message)
        sys.stdout.flush()

    def parse_trimmomatic_steps(self, input_params):
        # validate input parameters and return string defining trimmomatic steps

        parameter_string = ''

        if 'read_type' not in input_params and input_params['read_type'] is not None:
            raise ValueError('read_type not defined')
        elif input_params['read_type'] not in ('PE', 'SE'):
            raise ValueError('read_type must be PE or SE')

        if 'quality_encoding' not in input_params and input_params['quality_encoding'] is not None:
            raise ValueError('quality_encoding not defined')
        elif input_params['quality_encoding'] not in ('phred33', 'phred64'):
            raise ValueError('quality_encoding must be phred33 or phred64')

        # set adapter trimming
        if ('adapterFa' in input_params and input_params['adapterFa'] is not None and
            'seed_mismatches' in input_params and input_params['seed_mismatches'] is not None and
            'palindrome_clip_threshold' in input_params and input_params['quality_encoding'] is not None and
            'simple_clip_threshold' in input_params and input_params['simple_clip_threshold'] is not None):
            parameter_string = ("ILLUMINACLIP:" + self.ADAPTER_DIR +
                                ":".join((str(input_params['adapterFa']),
                                          str(input_params['seed_mismatches']),
                                          str(input_params['palindrome_clip_threshold']),
                                          str(input_params['simple_clip_threshold']))) + " ")
        elif ( ('adapterFa' in input_params and input_params['adapterFa'] is not None) or
               ('seed_mismatches' in input_params and input_params['seed_mismatches'] is not None) or
               ('palindrome_clip_threshold' in input_params and input_params['palindrome_clip_threshold'] is not None) or
               ('simple_clip_threshold' in input_params and input_params['simple_clip_threshold'] is not None) ):
            raise ValueError('Adapter Clipping requires Adapter, Seed Mismatches, Palindrome Clip Threshold and Simple Clip Threshold')

        # set Crop
        if 'crop_length' in input_params and input_params['crop_length'] is not None \
                and int(input_params['crop_length']) > 0:
            parameter_string += 'CROP:' + str(input_params['crop_length']) + ' '

        # set Headcrop
        if 'head_crop_length' in input_params and input_params['head_crop_length'] is not None \
                and input_params['head_crop_length'] > 0:
            parameter_string += 'HEADCROP:' + str(input_params['head_crop_length']) + ' '

        # set Leading
        if 'leading_min_quality' in input_params and input_params['leading_min_quality'] is not None \
                and input_params['leading_min_quality'] > 0:
            parameter_string += 'LEADING:' + str(input_params['leading_min_quality']) + ' '

        # set Trailing
        if 'trailing_min_quality' in input_params and input_params['trailing_min_quality'] is not None \
                and input_params['trailing_min_quality'] > 0:
            parameter_string += 'TRAILING:' + str(input_params['trailing_min_quality']) + ' '

        # set sliding window
        if 'sliding_window_size' in input_params and input_params['sliding_window_size'] is not None \
                and input_params['sliding_window_size'] > 0 \
                and 'sliding_window_min_quality' in input_params and input_params['sliding_window_min_quality'] is not None \
                and input_params['sliding_window_min_quality'] > 0:
            parameter_string += 'SLIDINGWINDOW:' + str(input_params['sliding_window_size']) + ":" + str(input_params['sliding_window_min_quality']) + ' '
        elif ('sliding_window_size' in input_params and input_params['sliding_window_size'] is not None \
                and input_params['sliding_window_size'] > 0) \
             or ('sliding_window_min_quality' in input_params and input_params['sliding_window_min_quality'] is not None \
                and input_params['sliding_window_size'] > 0):
            raise ValueError('Sliding Window filtering requires both Window Size and Window Minimum Quality to be set')

        # set min length
        if 'min_length' in input_params and input_params['min_length'] is not None \
                and input_params['min_length'] > 0:
            parameter_string += 'MINLEN:' + str(input_params['min_length']) + ' '

        if parameter_string == '':
            raise ValueError('No filtering/trimming steps specified!')

        return parameter_string

    #END_CLASS_HEADER

    # config contains contents of config file in a hash or None if it couldn't
    # be found
    def __init__(self, config):
        #BEGIN_CONSTRUCTOR
        self.workspaceURL = config['workspace-url']
        self.shockURL = config['shock-url']
        self.scratch = os.path.abspath(config['scratch'])
        self.handleURL = config['handle-service-url']
        self.serviceWizardURL = config['service-wizard-url']

        self.callbackURL = os.environ.get('SDK_CALLBACK_URL', None)
        if self.callbackURL is None:
            raise ValueError("SDK_CALLBACK_URL not set in environment")

        if not os.path.exists(self.scratch):
            os.makedirs(self.scratch)
        os.chdir(self.scratch)
        #END_CONSTRUCTOR
        pass

    def runTrimmomatic(self, ctx, input_params):
        """
        :param input_params: instance of type "runTrimmomaticInput"
           (runTrimmomatic() ** ** to backend a KBase App, potentially
           operating on ReadSets) -> structure: parameter "input_ws" of type
           "workspace_name" (** Common types), parameter "input_reads_ref" of
           type "data_obj_ref", parameter "output_ws" of type
           "workspace_name" (** Common types), parameter "output_reads_name"
           of type "data_obj_name", parameter "read_type" of String,
           parameter "quality_encoding" of String, parameter "adapter_clip"
           of type "AdapterClip_Options" -> structure: parameter "adapterFa"
           of String, parameter "seed_mismatches" of Long, parameter
           "palindrome_clip_threshold" of Long, parameter
           "simple_clip_threshold" of Long, parameter "sliding_window" of
           type "SlidingWindow_Options" (parameter groups) -> structure:
           parameter "sliding_window_size" of Long, parameter
           "sliding_window_min_quality" of Long, parameter
           "leading_min_quality" of Long, parameter "trailing_min_quality" of
           Long, parameter "crop_length" of Long, parameter
           "head_crop_length" of Long, parameter "min_length" of Long
        :returns: instance of type "runTrimmomaticOutput" -> structure:
           parameter "report_name" of String, parameter "report_ref" of String
        """
        # ctx is the context object
        # return variables are: output
        #BEGIN runTrimmomatic
        console = []
        self.log(console, 'Running runTrimmomatic with parameters: ')
        self.log(console, "\n"+pformat(input_params))

        token = ctx['token']
        env = os.environ.copy()
        env['KB_AUTH_TOKEN'] = token

        SERVICE_VER = 'release'

        # param checks
        if ('output_ws' not in input_params or input_params['output_ws'] is None):
            input_params['output_ws'] = input_params['input_ws']

        required_params = ['input_reads_ref',
                           'output_ws',
                           'output_reads_name',
                           'read_type'
                          ]
        for required_param in required_params:
            if required_param not in input_params or input_params[required_param] == None:
                raise ValueError ("Must define required param: '"+required_param+"'")

        # load provenance
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        provenance[0]['input_ws_objects']=[str(input_params['input_reads_ref'])]

        # set up and run execTrimmomatic()
        #
        execTrimmomaticParams = { 'input_reads_ref': str(input_params['input_reads_ref']),
                                  'output_ws': input_params['output_ws'],
                                  'output_reads_name': input_params['output_reads_name'],
                                  'read_type': input_params['read_type'],
                                 }

        if 'quality_encoding' in input_params:
            execTrimmomaticParams['quality_encoding'] = input_params['quality_encoding']

        # adapter_clip grouped params
        if 'adapter_clip' in input_params and input_params['adapter_clip'] != None:
            if 'adapterFa' in input_params['adapter_clip']:
                execTrimmomaticParams['adapterFa'] = input_params['adapter_clip']['adapterFa']
            else:
                execTrimmomaticParams['adapterFa'] = None

            if 'seed_mismatches' in input_params['adapter_clip']:
                execTrimmomaticParams['seed_mismatches'] = input_params['adapter_clip']['seed_mismatches']
            else:
                execTrimmomaticParams['seed_mismatches'] = None

            if 'palindrome_clip_threshold' in input_params['adapter_clip']:
                execTrimmomaticParams['palindrome_clip_threshold'] = input_params['adapter_clip']['palindrome_clip_threshold']
            else:
                execTrimmomaticParams['palindrome_clip_threshold'] = None

            if 'simple_clip_threshold' in input_params['adapter_clip']:
                execTrimmomaticParams['simple_clip_threshold'] = input_params['adapter_clip']['simple_clip_threshold']
            else:
                execTrimmomaticParams['simple_clip_threshold'] = None

        # sliding window
        if 'sliding_window' in input_params:
            if 'sliding_window_size' in input_params['sliding_window']:
                execTrimmomaticParams['sliding_window_size'] = input_params['sliding_window']['sliding_window_size']
            else:
                execTrimmomaticParams['sliding_window_size'] = None

            if 'sliding_window_min_quality' in input_params['sliding_window']:
                execTrimmomaticParams['sliding_window_min_quality'] = input_params['sliding_window']['sliding_window_min_quality']
            else:
                execTrimmomaticParams['sliding_window_min_quality'] = None

        # remaining params
        if 'leading_min_quality' in input_params:
            execTrimmomaticParams['leading_min_quality'] = input_params['leading_min_quality']
        if 'trailing_min_quality' in input_params:
            execTrimmomaticParams['trailing_min_quality'] = input_params['trailing_min_quality']
        if 'crop_length' in input_params:
            execTrimmomaticParams['crop_length'] = input_params['crop_length']
        if 'head_crop_length' in input_params:
            execTrimmomaticParams['head_crop_length'] = input_params['head_crop_length']
        if 'min_length' in input_params:
            execTrimmomaticParams['min_length'] = input_params['min_length']

        # RUN
        trimmomatic_retVal = self.execTrimmomatic (ctx, execTrimmomaticParams)[0]


        # build report
        #
        reportName = 'kb_trimmomatic_report_'+str(uuid.uuid4())

        reportObj = {'objects_created': [],
                     #'text_message': '',  # or is it 'message'?
                     'message': '',  # or is it 'text_message'?
                     'direct_html': '',
                     'direct_html_index': 0,
                     'file_links': [],
                     'html_links': [],
                     'workspace_name': input_params['input_ws'],
                     'report_object_name': reportName
                     }


        # text report (replaced by HTML report)
        try:
            #reportObj['text_message'] = trimmomatic_retVal['report']
            #reportObj['message'] = trimmomatic_retVal['report']
            msg = trimmomatic_retVal['report']
        except:
            raise ValueError ("no report generated by execTrimmomatic()")

        # parse text report
        report_data = []
        report_field_order = []
        report_lib_refs = []
        report_lib_names = []
        lib_i = -1

        # This is some powerful brute force nonsense, but it should be okay.
        se_report_re = re.compile('^Input Reads:\s*(\d+)\s*Surviving:\s*(\d+)\s*\(\d+\.\d+\%\)\s*Dropped:\s*(\d+)\s*\(\d+\.\d+\%\)')
        for line in trimmomatic_retVal['report'].split("\n"):
            if line.startswith("RUNNING"):
                lib_i += 1
                lib_ids = re.sub("RUNNING TRIMMOMATIC ON LIBRARY: ", '', line)
                [ref, name] = lib_ids.split(" ")
                report_lib_refs.append(ref)
                report_lib_names.append(name)
                report_data.append({})
                report_field_order.append([])
            elif line.startswith("-"):
                continue
            elif len(line) == 0:
                continue
            else:
                m = se_report_re.match(line)
                if m and len(m.groups()) == 3:
                    report_field_order[lib_i] = ['Input Reads', 'Surviving', 'Dropped']
                    report_data[lib_i] = dict(zip(report_field_order[lib_i], m.groups()))
                try:
                    [f_name, val] = line.split(': ')
                    int_val = int(val)
                    report_field_order[lib_i].append(f_name)
                    report_data[lib_i][f_name] = int_val
                except ValueError:
                    print("Can't parse [" + line + "] (lib_i=" + str(lib_i) + ")")

        # html report
        sp = '&nbsp;'
        text_color = "#606060"
        bar_color = "lightblue"
        bar_width = 100
        bar_char = "."
        bar_fontsize = "-2"
        row_spacing = "-2"

        html_report_lines = ['<html>']
        html_report_lines += ['<body bgcolor="white">']

#        result_data_order = ['foobarfoo', 'animalcules', 'chicken', 'applesauce']
#        result_data = { 'foobarfoo': 197,
#                        'animalcules': 234,
#                        'chicken': 14,
#                        'applesauce': 1
#                        }

        for lib_i in range(len(report_data)):
            html_report_lines += ['<p><b><font color="'+text_color+'">TRIMMOMATIC RESULTS FOR '+str(report_lib_names[lib_i])+' (object '+str(report_lib_refs[lib_i])+')</font></b><br>'+"\n"]
            high_val = 0
            if not len(report_field_order[lib_i]):
                html_report_lines += ['All reads were trimmed - no new reads object created.']
            else:
                html_report_lines += ['<table cellpadding=0 cellspacing=0 border=0>']
                html_report_lines += ['<tr><td></td><td>'+sp+sp+sp+sp+'</td><td></td><td>'+sp+sp+'</td></tr>']
                for f_name in report_field_order[lib_i]:
                    if report_data[lib_i][f_name] > high_val:
                        high_val = report_data[lib_i][f_name]
                for f_name in report_field_order[lib_i]:

                    percent = round(float(report_data[lib_i][f_name])/float(high_val)*100, 1)

                    this_width = int(round(float(bar_width)*float(report_data[lib_i][f_name])/float(high_val), 0))
                    #self.log(console,"this_width: "+str(this_width)+" report_data: "+str(report_data[lib_i][f_name])+" calc: "+str(float(width)*float(report_data[lib_i][f_name])/float(high_val)))  # DEBUG
                    if this_width < 1:
                        if report_data[lib_i][f_name] > 0:
                            this_width = 1
                        else:
                            this_width = 0
                    html_report_lines += ['<tr>']
                    html_report_lines += ['    <td align=right><font color="'+text_color+'">'+str(f_name)+'</font></td><td></td>']
                    html_report_lines += ['    <td align=right><font color="'+text_color+'">'+str(report_data[lib_i][f_name])+'</font></td><td></td>']
                    html_report_lines += ['    <td align=right><font color="'+text_color+'">'+'('+str(percent)+'%)'+sp+sp+'</font></td><td></td>']

                    if this_width > 0:
                        for tic in range(this_width):
                            html_report_lines += ['    <td bgcolor="'+bar_color+'"><font size='+bar_fontsize+' color="'+bar_color+'">'+bar_char+'</font></td>']
                    html_report_lines += ['</tr>']
                    html_report_lines += ['<tr><td><font size='+row_spacing+'>'+sp+'</font></td></tr>']

                html_report_lines += ['</table>']
                html_report_lines += ['<p>']
        html_report_lines += ['</body>']
        html_report_lines += ['</html>']

        reportObj['direct_html'] = "\n".join(html_report_lines)

        # trimmed object
        if trimmomatic_retVal['output_filtered_ref'] != None:
            try:
                # DEBUG
                #self.log(console,"OBJECT CREATED: '"+str(trimmomatic_retVal['output_filtered_ref'])+"'")

                reportObj['objects_created'].append({'ref':trimmomatic_retVal['output_filtered_ref'],
                                                     'description':'Trimmed Reads'})
            except:
                raise ValueError ("failure saving trimmed output")
        else:
            self.log(console, "No trimmed output generated by execTrimmomatic()")


        # unpaired fwd
        if trimmomatic_retVal['output_unpaired_fwd_ref'] != None:
            try:
                reportObj['objects_created'].append({'ref':trimmomatic_retVal['output_unpaired_fwd_ref'],
                                                     'description':'Trimmed Unpaired Forward Reads'})
            except:
                raise ValueError ("failure saving unpaired fwd output")
        else:
            pass

        # unpaired rev
        if trimmomatic_retVal['output_unpaired_rev_ref'] != None:
            try:
                reportObj['objects_created'].append({'ref':trimmomatic_retVal['output_unpaired_rev_ref'],
                                                     'description':'Trimmed Unpaired Reverse Reads'})
            except:
                raise ValueError ("failure saving unpaired fwd output")
        else:
            pass


        # save report object
        #
        report = KBaseReport(self.callbackURL, token=ctx['token'], service_ver=SERVICE_VER)
        #report_info = report.create({'report':reportObj, 'workspace_name':input_params['input_ws']})
        report_info = report.create_extended_report(reportObj)

        output = { 'report_name': report_info['name'], 'report_ref': report_info['ref'] }
        #END runTrimmomatic

        # At some point might do deeper type checking...
        if not isinstance(output, dict):
            raise ValueError('Method runTrimmomatic return value ' +
                             'output is not type dict as required.')
        # return the results
        return [output]

    def execTrimmomatic(self, ctx, input_params):
        """
        :param input_params: instance of type "execTrimmomaticInput"
           (execTrimmomatic() ** ** the local method that runs Trimmomatic on
           each read library) -> structure: parameter "input_reads_ref" of
           type "data_obj_ref", parameter "output_ws" of type
           "workspace_name" (** Common types), parameter "output_reads_name"
           of type "data_obj_name", parameter "read_type" of String,
           parameter "adapterFa" of String, parameter "seed_mismatches" of
           Long, parameter "palindrome_clip_threshold" of Long, parameter
           "simple_clip_threshold" of Long, parameter "quality_encoding" of
           String, parameter "sliding_window_size" of Long, parameter
           "sliding_window_min_quality" of Long, parameter
           "leading_min_quality" of Long, parameter "trailing_min_quality" of
           Long, parameter "crop_length" of Long, parameter
           "head_crop_length" of Long, parameter "min_length" of Long
        :returns: instance of type "execTrimmomaticOutput" -> structure:
           parameter "output_filtered_ref" of type "data_obj_ref", parameter
           "output_unpaired_fwd_ref" of type "data_obj_ref", parameter
           "output_unpaired_rev_ref" of type "data_obj_ref", parameter
           "report" of String
        """
        # ctx is the context object
        # return variables are: output
        #BEGIN execTrimmomatic
        console = []
        self.log(console, 'Running execTrimmomatic with parameters: ')
        self.log(console, "\n"+pformat(input_params))
        report = ''
        trimmomatic_retVal = dict()
        trimmomatic_retVal['output_filtered_ref'] = None
        trimmomatic_retVal['output_unpaired_fwd_ref'] = None
        trimmomatic_retVal['output_unpaired_rev_ref'] = None

        token = ctx['token']
        wsClient = workspaceService(self.workspaceURL, token=token)
        headers = {'Authorization': 'OAuth '+token}
        env = os.environ.copy()
        env['KB_AUTH_TOKEN'] = token

        # param checks
        required_params = ['input_reads_ref',
                           'output_ws',
                           'output_reads_name',
                           'read_type'
                          ]
        for required_param in required_params:
            if required_param not in input_params or input_params[required_param] == None:
                raise ValueError ("Must define required param: '"+required_param+"'")

        # load provenance
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        # add additional info to provenance here, in this case the input data object reference
        provenance[0]['input_ws_objects']=[str(input_params['input_reads_ref'])]

        # Determine whether read library or read set is input object
        #
        try:
            # object_info tuple
            [OBJID_I, NAME_I, TYPE_I, SAVE_DATE_I, VERSION_I, SAVED_BY_I, WSID_I, WORKSPACE_I, CHSUM_I, SIZE_I, META_I] = range(11)

            input_reads_obj_info = wsClient.get_object_info_new ({'objects':[{'ref':input_params['input_reads_ref']}]})[0]
            input_reads_obj_type = input_reads_obj_info[TYPE_I]
            #input_reads_obj_version = input_reads_obj_info[VERSION_I]  # this is object version, not type version

        except Exception as e:
            raise ValueError('Unable to get read library object from workspace: (' + str(input_params['input_reads_ref']) +')' + str(e))

        #self.log (console, "B4 TYPE: '"+str(input_reads_obj_type)+"' VERSION: '"+str(input_reads_obj_version)+"'")
        input_reads_obj_type = re.sub ('-[0-9]+\.[0-9]+$', "", input_reads_obj_type)  # remove trailing version
        #self.log (console, "AF TYPE: '"+str(input_reads_obj_type)+"' VERSION: '"+str(input_reads_obj_version)+"'")

        acceptable_types = ["KBaseSets.ReadsSet", "KBaseRNASeq.RNASeqSampleSet", "KBaseFile.PairedEndLibrary", "KBaseFile.SingleEndLibrary", "KBaseAssembly.PairedEndLibrary", "KBaseAssembly.SingleEndLibrary"]
        if input_reads_obj_type not in acceptable_types:
            raise ValueError ("Input reads of type: '"+input_reads_obj_type+"'.  Must be one of "+", ".join(acceptable_types))


        # get set
        #
        readsSet_ref_list = []
        readsSet_names_list = []
        if input_reads_obj_type in ["KBaseSets.ReadsSet", "KBaseRNASeq.RNASeqSampleSet"]:
            try:
                #self.log (console, "INPUT_READS_REF: '"+input_params['input_reads_ref']+"'")  # DEBUG
                #setAPI_Client = SetAPI (url=self.callbackURL, token=ctx['token'])  # for SDK local.  doesn't work for SetAPI
                setAPI_Client = SetAPI (url=self.serviceWizardURL, token=ctx['token'], service_ver='beta')  # for dynamic service
                input_readsSet_obj = setAPI_Client.get_reads_set_v1 ({'ref':input_params['input_reads_ref'],'include_item_info':1})

            except Exception as e:
                raise ValueError('SetAPI FAILURE: Unable to get read library set object from workspace: (' + str(input_params['input_reads_ref'])+")\n" + str(e))
            for readsLibrary_obj in input_readsSet_obj['data']['items']:
                readsSet_ref_list.append(readsLibrary_obj['ref'])
                NAME_I = 1
                readsSet_names_list.append(readsLibrary_obj['info'][NAME_I])
        else:
            readsSet_ref_list = [input_params['input_reads_ref']]
            NAME_I = 1
            readsSet_names_list = [input_reads_obj_info[NAME_I]]


        # Iterate through readsLibrary members of set
        #
        report = ''
        trimmed_readsSet_ref       = None
        unpaired_fwd_readsSet_ref  = None
        unpaired_rev_readsSet_ref  = None
        trimmed_readsSet_refs      = []
        unpaired_fwd_readsSet_refs = []
        unpaired_rev_readsSet_refs = []

        for reads_item_i,input_reads_library_ref in enumerate(readsSet_ref_list):
            execTrimmomaticParams = { 'input_reads_ref': input_reads_library_ref,
                                      'output_ws': input_params['output_ws']
                                      }
            optional_params = ['read_type',
                               'adapterFa',
                               'seed_mismatches',
                               'palindrome_clip_threshold',
                               'simple_clip_threshold',
                               'quality_encoding',
                               'sliding_window_size',
                               'sliding_window_min_quality',
                               'leading_min_quality',
                               'trailing_min_quality',
                               'crop_length',
                               'head_crop_length',
                               'min_length'
                               ]
            for arg in optional_params:
                if arg in input_params:
                    execTrimmomaticParams[arg] = input_params[arg]

            if input_reads_obj_type not in ["KBaseSets.ReadsSet", "KBaseRNASeq.RNASeqSampleSet"]:
                execTrimmomaticParams['output_reads_name'] = input_params['output_reads_name']
            else:
                execTrimmomaticParams['output_reads_name'] = readsSet_names_list[reads_item_i]+'_trimm'

            report += "RUNNING TRIMMOMATIC ON LIBRARY: "+str(input_reads_library_ref)+" "+str(readsSet_names_list[reads_item_i])+"\n"
            report += "-----------------------------------------------------------------------------------\n\n"

            trimmomaticSingleLibrary_retVal = self.execTrimmomaticSingleLibrary (ctx, execTrimmomaticParams)[0]

            report += trimmomaticSingleLibrary_retVal['report']+"\n\n"
            trimmed_readsSet_refs.append (trimmomaticSingleLibrary_retVal['output_filtered_ref'])
            unpaired_fwd_readsSet_refs.append (trimmomaticSingleLibrary_retVal['output_unpaired_fwd_ref'])
            unpaired_rev_readsSet_refs.append (trimmomaticSingleLibrary_retVal['output_unpaired_rev_ref'])


        # Just one Library
        if input_reads_obj_type not in ["KBaseSets.ReadsSet", "KBaseRNASeq.RNASeqSampleSet"]:

            # create return output object
            output = { 'report': report,
                       'output_filtered_ref': trimmed_readsSet_refs[0],
                       'output_unpaired_fwd_ref': unpaired_fwd_readsSet_refs[0],
                       'output_unpaired_rev_ref': unpaired_rev_readsSet_refs[0],
                     }
        # ReadsSet
        else:

            # save trimmed readsSet
            some_trimmed_output_created = False
            items = []
            for i,lib_ref in enumerate(trimmed_readsSet_refs):   # FIX: assumes order maintained
                if lib_ref == None:
                    #items.append(None)  # can't have 'None' items in ReadsSet
                    continue
                else:
                    some_trimmed_output_created = True
                    try:
                        label = input_readsSet_obj['data']['items'][i]['label']
                    except:
                        NAME_I = 1
                        label = wsClient.get_object_info_new ({'objects':[{'ref':lib_ref}]})[0][NAME_I]
                    label = label + "_Trimm_paired"

                    items.append({'ref': lib_ref,
                                  'label': label
                                  #'data_attachment': ,
                                  #'info':
                                      })
            if some_trimmed_output_created:
                if input_params['read_type'] == 'SE':
                    reads_desc_ext = " Trimmomatic trimmed SingleEndLibrary"
                    reads_name_ext = "_trimm"
                else:
                    reads_desc_ext = " Trimmomatic trimmed paired reads"
                    reads_name_ext = "_trimm_paired"
                output_readsSet_obj = { 'description': input_readsSet_obj['data']['description']+reads_desc_ext,
                                        'items': items
                                        }
                output_readsSet_name = str(input_params['output_reads_name'])+reads_name_ext
                trimmed_readsSet_ref = setAPI_Client.save_reads_set_v1 ({'workspace_name': input_params['output_ws'],
                                                                         'output_object_name': output_readsSet_name,
                                                                         'data': output_readsSet_obj
                                                                         })['set_ref']
            else:
                self.log(console, "No trimmed output created")
                # raise ValueError ("No trimmed output created")


            # save unpaired forward readsSet
            some_unpaired_fwd_output_created = False
            if len(unpaired_fwd_readsSet_refs) > 0:
                items = []
                for i,lib_ref in enumerate(unpaired_fwd_readsSet_refs):  # FIX: assumes order maintained
                    if lib_ref == None:
                        #items.append(None)  # can't have 'None' items in ReadsSet
                        continue
                    else:
                        some_unpaired_fwd_output_created = True
                        try:
                            if len(unpaired_fwd_readsSet_refs) == len(input_readsSet_obj['data']['items']):
                                label = input_readsSet_obj['data']['items'][i]['label']
                            else:
                                NAME_I = 1
                                label = wsClient.get_object_info_new ({'objects':[{'ref':lib_ref}]})[0][NAME_I]
                        except:
                            NAME_I = 1
                            label = wsClient.get_object_info_new ({'objects':[{'ref':lib_ref}]})[0][NAME_I]
                        label = label + "_Trimm_unpaired_fwd"

                        items.append({'ref': lib_ref,
                                      'label': label
                                      #'data_attachment': ,
                                      #'info':
                                          })
                if some_unpaired_fwd_output_created:
                    output_readsSet_obj = { 'description': input_readsSet_obj['data']['description']+" Trimmomatic unpaired fwd reads",
                                            'items': items
                                            }
                    output_readsSet_name = str(input_params['output_reads_name'])+'_trimm_unpaired_fwd'
                    unpaired_fwd_readsSet_ref = setAPI_Client.save_reads_set_v1 ({'workspace_name': input_params['output_ws'],
                                                                                  'output_object_name': output_readsSet_name,
                                                                                  'data': output_readsSet_obj
                                                                                  })['set_ref']
                else:
                    self.log (console, "no unpaired_fwd readsLibraries created")
                    unpaired_fwd_readsSet_ref = None

            # save unpaired reverse readsSet
            some_unpaired_rev_output_created = False
            if len(unpaired_rev_readsSet_refs) > 0:
                items = []
                for i,lib_ref in enumerate(unpaired_fwd_readsSet_refs):  # FIX: assumes order maintained
                    if lib_ref == None:
                        #item`s.append(None)  # can't have 'None' items in ReadsSet
                        continue
                    else:
                        some_unpaired_rev_output_created = True
                        try:
                            if len(unpaired_rev_readsSet_refs) == len(input_readsSet_obj['data']['items']):
                                label = input_readsSet_obj['data']['items'][i]['label']
                            else:
                                NAME_I = 1
                                label = wsClient.get_object_info_new ({'objects':[{'ref':lib_ref}]})[0][NAME_I]

                        except:
                            NAME_I = 1
                            label = wsClient.get_object_info_new ({'objects':[{'ref':lib_ref}]})[0][NAME_I]
                        label = label + "_Trimm_unpaired_rev"

                        items.append({'ref': lib_ref,
                                      'label': label
                                      #'data_attachment': ,
                                      #'info':
                                          })
                if some_unpaired_rev_output_created:
                    output_readsSet_obj = { 'description': input_readsSet_obj['data']['description']+" Trimmomatic unpaired rev reads",
                                            'items': items
                                            }
                    output_readsSet_name = str(input_params['output_reads_name'])+'_trimm_unpaired_rev'
                    unpaired_rev_readsSet_ref = setAPI_Client.save_reads_set_v1 ({'workspace_name': input_params['output_ws'],
                                                                                  'output_object_name': output_readsSet_name,
                                                                                  'data': output_readsSet_obj
                                                                                  })['set_ref']
                else:
                    self.log (console, "no unpaired_rev readsLibraries created")
                    unpaired_rev_readsSet_ref = None


            # create return output object
            output = { 'report': report,
                       'output_filtered_ref': trimmed_readsSet_ref,
                       'output_unpaired_fwd_ref': unpaired_fwd_readsSet_ref,
                       'output_unpaired_rev_ref': unpaired_rev_readsSet_ref
                     }

        #END execTrimmomatic

        # At some point might do deeper type checking...
        if not isinstance(output, dict):
            raise ValueError('Method execTrimmomatic return value ' +
                             'output is not type dict as required.')
        # return the results
        return [output]

    def execTrimmomaticSingleLibrary(self, ctx, input_params):
        """
        :param input_params: instance of type "execTrimmomaticInput"
           (execTrimmomatic() ** ** the local method that runs Trimmomatic on
           each read library) -> structure: parameter "input_reads_ref" of
           type "data_obj_ref", parameter "output_ws" of type
           "workspace_name" (** Common types), parameter "output_reads_name"
           of type "data_obj_name", parameter "read_type" of String,
           parameter "adapterFa" of String, parameter "seed_mismatches" of
           Long, parameter "palindrome_clip_threshold" of Long, parameter
           "simple_clip_threshold" of Long, parameter "quality_encoding" of
           String, parameter "sliding_window_size" of Long, parameter
           "sliding_window_min_quality" of Long, parameter
           "leading_min_quality" of Long, parameter "trailing_min_quality" of
           Long, parameter "crop_length" of Long, parameter
           "head_crop_length" of Long, parameter "min_length" of Long
        :returns: instance of type "execTrimmomaticOutput" -> structure:
           parameter "output_filtered_ref" of type "data_obj_ref", parameter
           "output_unpaired_fwd_ref" of type "data_obj_ref", parameter
           "output_unpaired_rev_ref" of type "data_obj_ref", parameter
           "report" of String
        """
        # ctx is the context object
        # return variables are: output
        #BEGIN execTrimmomaticSingleLibrary
        console = []
        self.log(console, 'Running Trimmomatic with parameters: ')
        self.log(console, "\n"+pformat(input_params))
        report = ''
        retVal = dict()
        retVal['output_filtered_ref'] = None
        retVal['output_unpaired_fwd_ref'] = None
        retVal['output_unpaired_rev_ref'] = None

        token = ctx['token']
        wsClient = workspaceService(self.workspaceURL, token=token)
        headers = {'Authorization': 'OAuth '+token}
        env = os.environ.copy()
        env['KB_AUTH_TOKEN'] = token

        # param checks
        required_params = ['input_reads_ref',
                           'output_ws',
                           'output_reads_name',
                           'read_type'
                          ]
        for required_param in required_params:
            if required_param not in input_params or input_params[required_param] == None:
                raise ValueError ("Must define required param: '"+required_param+"'")

        # and param defaults
        defaults = {
            'quality_encoding':           'phred33',
            'seed_mismatches':            '0', # '2',
            'palindrome_clip_threshold':  '0', # '3',
            'simple_clip_threshold':      '0', # '10',
            'crop_length':                '0',
            'head_crop_length':           '0',
            'leading_min_quality':        '0', # '3',
            'trailing_min_quality':       '0', # '3',
            'sliding_window_size':        '0', # '4',
            'sliding_window_min_quality': '0', # '15',
            'min_length':                 '0', # '36'
        }
        for arg in defaults.keys():
            if arg not in input_params or input_params[arg] is None or input_params[arg] == '':
                input_params[arg] = defaults[arg]

        # conditional arg behavior
        arg = 'adapterFa'
        if arg not in input_params or input_params[arg] is None or input_params[arg] == '':
            input_params['adapterFa'] = None
            input_params['seed_mismatches'] = None
            input_params['palindrome_clip_threshold'] = None
            input_params['simple_clip_threshold'] = None


        #load provenance
        provenance = [{}]
        if 'provenance' in ctx:
            provenance = ctx['provenance']
        # add additional info to provenance here, in this case the input data object reference
        provenance[0]['input_ws_objects']=[str(input_params['input_reads_ref'])]

        # Determine whether read library is of correct type
        #
        try:
            # object_info tuple
            [OBJID_I, NAME_I, TYPE_I, SAVE_DATE_I, VERSION_I, SAVED_BY_I, WSID_I, WORKSPACE_I, CHSUM_I, SIZE_I, META_I] = range(11)

            input_reads_obj_info = wsClient.get_object_info_new ({'objects':[{'ref':input_params['input_reads_ref']}]})[0]
            input_reads_obj_type = input_reads_obj_info[TYPE_I]
            #input_reads_obj_version = input_reads_obj_info[VERSION_I]  # this is object version, not type version

        except Exception as e:
            raise ValueError('Unable to get read library object from workspace: (' + str(input_params['input_reads_ref']) +')' + str(e))

        #self.log (console, "B4 TYPE: '"+str(input_reads_obj_type)+"' VERSION: '"+str(input_reads_obj_version)+"'")
        input_reads_obj_type = re.sub ('-[0-9]+\.[0-9]+$', "", input_reads_obj_type)  # remove trailing version
        #self.log (console, "AF TYPE: '"+str(input_reads_obj_type)+"' VERSION: '"+str(input_reads_obj_version)+"'")

        acceptable_types = ["KBaseFile.PairedEndLibrary", "KBaseAssembly.PairedEndLibrary", "KBaseAssembly.SingleEndLibrary", "KBaseFile.SingleEndLibrary"]
        if input_reads_obj_type not in acceptable_types:
            raise ValueError ("Input reads of type: '"+input_reads_obj_type+"'.  Must be one of "+", ".join(acceptable_types))


        # Confirm user is paying attention (matters because Trimmomatic params are very different for PairedEndLibary and SingleEndLibrary
        #
        if input_params['read_type'] == 'PE' \
                and (input_reads_obj_type == 'KBaseAssembly.SingleEndLibrary' \
                     or input_reads_obj_type == 'KBaseFile.SingleEndLibrary'):
            raise ValueError ("read_type set to 'Paired End' but object is SingleEndLibrary")
        if input_params['read_type'] == 'SE' \
                and (input_reads_obj_type == 'KBaseAssembly.PairedEndLibrary' \
                     or input_reads_obj_type == 'KBaseFile.PairedEndLibrary'):
            raise ValueError ("read_type set to 'Single End' but object is PairedEndLibrary")


        # Let's rock!
        #
        trimmomatic_params  = self.parse_trimmomatic_steps(input_params)
        trimmomatic_options = str(input_params['read_type']) + ' -' + str(input_params['quality_encoding'])

        self.log(console, pformat(trimmomatic_params))
        self.log(console, pformat(trimmomatic_options))


        # Instatiate ReadsUtils
        #
        try:
            readsUtils_Client = ReadsUtils (url=self.callbackURL, token=ctx['token'])  # SDK local

            readsLibrary = readsUtils_Client.download_reads ({'read_libraries': [input_params['input_reads_ref']],
                                                             'interleaved': 'false'
                                                             })
        except Exception as e:
            raise ValueError('Unable to get read library object from workspace: (' + str(input_params['input_reads_ref']) +")\n" + str(e))


        if input_params['read_type'] == 'PE':

            # Download reads Libs to FASTQ files
            input_fwd_file_path = readsLibrary['files'][input_params['input_reads_ref']]['files']['fwd']
            input_rev_file_path = readsLibrary['files'][input_params['input_reads_ref']]['files']['rev']
            sequencing_tech     = readsLibrary['files'][input_params['input_reads_ref']]['sequencing_tech']


            # DEBUG
#            self.log (console, "FWD_INPUT\n")
#            fwd_reads_handle = open (input_fwd_file_path, 'r')
#            for line_i in range(20):
#                self.log (console, fwd_reads_handle.readline())
#            fwd_reads_handle.close ()
#            self.log (console, "REV_INPUT\n")
#            rev_reads_handle = open (input_rev_file_path, 'r')
#            for line_i in range(20):
#                self.log (console, rev_reads_handle.readline())
#            rev_reads_handle.close ()


            # Run Trimmomatic
            #
            self.log(console, 'Starting Trimmomatic')
            input_fwd_file_path = re.sub ("\.fq$", "", input_fwd_file_path)
            input_fwd_file_path = re.sub ("\.FQ$", "", input_fwd_file_path)
            input_rev_file_path = re.sub ("\.fq$", "", input_rev_file_path)
            input_rev_file_path = re.sub ("\.FQ$", "", input_rev_file_path)
            input_fwd_file_path = re.sub ("\.fastq$", "", input_fwd_file_path)
            input_fwd_file_path = re.sub ("\.FASTQ$", "", input_fwd_file_path)
            input_rev_file_path = re.sub ("\.fastq$", "", input_rev_file_path)
            input_rev_file_path = re.sub ("\.FASTQ$", "", input_rev_file_path)
            output_fwd_paired_file_path   = input_fwd_file_path+"_trimm_fwd_paired.fastq"
            output_fwd_unpaired_file_path = input_fwd_file_path+"_trimm_fwd_unpaired.fastq"
            output_rev_paired_file_path   = input_rev_file_path+"_trimm_rev_paired.fastq"
            output_rev_unpaired_file_path = input_rev_file_path+"_trimm_rev_unpaired.fastq"
            input_fwd_file_path           = input_fwd_file_path+".fastq"
            input_rev_file_path           = input_rev_file_path+".fastq"

            cmdstring = " ".join( (self.TRIMMOMATIC, trimmomatic_options,
                            input_fwd_file_path,
                            input_rev_file_path,
                            output_fwd_paired_file_path,
                            output_fwd_unpaired_file_path,
                            output_rev_paired_file_path,
                            output_rev_unpaired_file_path,
                            trimmomatic_params) )

            cmdProcess = subprocess.Popen(cmdstring, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

            outputlines = []
            while True:
                line = cmdProcess.stdout.readline()
                outputlines.append(line)
                if not line: break
                self.log(console, line.replace('\n', ''))

            cmdProcess.stdout.close()
            cmdProcess.wait()
            self.log(console, 'return code: ' + str(cmdProcess.returncode) + '\n')
            if cmdProcess.returncode != 0:
                raise ValueError('Error running kb_trimmomatic, return code: ' +
                                 str(cmdProcess.returncode) + '\n')


            report += "\n".join(outputlines)
            #report += "cmdstring: " + cmdstring + " stdout: " + stdout + " stderr " + stderr

            # free up disk
            os.remove(input_fwd_file_path)
            os.remove(input_rev_file_path)

            #get read counts
            match = re.search(r'Input Read Pairs: (\d+).*?Both Surviving: (\d+).*?Forward Only Surviving: (\d+).*?Reverse Only Surviving: (\d+).*?Dropped: (\d+)', report)
            input_read_count = match.group(1)
            read_count_paired = match.group(2)
            read_count_forward_only = match.group(3)
            read_count_reverse_only = match.group(4)
            read_count_dropped = match.group(5)

            report = "\n".join( ('Input Read Pairs: '+ input_read_count,
                'Both Surviving: '+ read_count_paired,
                'Forward Only Surviving: '+ read_count_forward_only,
                'Reverse Only Surviving: '+ read_count_reverse_only,
                'Dropped: '+ read_count_dropped) )

            # upload paired reads
            if not os.path.isfile (output_fwd_paired_file_path) \
                or os.path.getsize (output_fwd_paired_file_path) == 0 \
                or not os.path.isfile (output_rev_paired_file_path) \
                or os.path.getsize (output_rev_paired_file_path) == 0:
                retVal['output_filtered_ref'] = None
                report += "\n\nNo reads were trimmed, so no trimmed reads object was generated."
            else:
                output_obj_name = input_params['output_reads_name']+'_paired'
                self.log(console, 'Uploading trimmed paired reads: '+output_obj_name)
                retVal['output_filtered_ref'] = readsUtils_Client.upload_reads ({ 'wsname': str(input_params['output_ws']),
                                                                                  'name': output_obj_name,
                                                                                  # remove sequencing_tech arg once ReadsUtils is updated to accept source_reads_ref
                                                                                  #'sequencing_tech': sequencing_tech,
                                                                                  'source_reads_ref': input_params['input_reads_ref'],
                                                                                  'fwd_file': output_fwd_paired_file_path,
                                                                                  'rev_file': output_rev_paired_file_path
                                                                                  })['obj_ref']

                # free up disk
                os.remove(output_fwd_paired_file_path)
                os.remove(output_rev_paired_file_path)


            # upload reads forward unpaired
            if not os.path.isfile (output_fwd_unpaired_file_path) \
                or os.path.getsize (output_fwd_unpaired_file_path) == 0:

                retVal['output_unpaired_fwd_ref'] = None
            else:
                output_obj_name = input_params['output_reads_name']+'_unpaired_fwd'
                self.log(console, '\nUploading trimmed unpaired forward reads: '+output_obj_name)
                retVal['output_unpaired_fwd_ref'] = readsUtils_Client.upload_reads ({ 'wsname': str(input_params['output_ws']),
                                                                                      'name': output_obj_name,
                                                                                      # remove sequencing_tech arg once ReadsUtils is updated to accept source_reads_ref
                                                                                      #'sequencing_tech': sequencing_tech,
                                                                                      'source_reads_ref': input_params['input_reads_ref'],
                                                                                      'fwd_file': output_fwd_unpaired_file_path
                                                                                      })['obj_ref']

                # free up disk
                os.remove(output_fwd_unpaired_file_path)

            # upload reads reverse unpaired
            if not os.path.isfile (output_rev_unpaired_file_path) \
                or os.path.getsize (output_rev_unpaired_file_path) == 0:

                retVal['output_unpaired_rev_ref'] = None
            else:
                output_obj_name = input_params['output_reads_name']+'_unpaired_rev'
                self.log(console, '\nUploading trimmed unpaired reverse reads: '+output_obj_name)
                retVal['output_unpaired_rev_ref'] = readsUtils_Client.upload_reads ({ 'wsname': str(input_params['output_ws']),
                                                                                      'name': output_obj_name,
                                                                                      # remove sequencing_tech arg once ReadsUtils is updated to accept source_reads_ref
                                                                                      #'sequencing_tech': sequencing_tech,
                                                                                      'source_reads_ref': input_params['input_reads_ref'],
                                                                                      'fwd_file': output_rev_unpaired_file_path
                                                                                      })['obj_ref']

                # free up disk
                os.remove(output_rev_unpaired_file_path)


        # SingleEndLibrary
        #
        else:
            self.log(console, "Downloading Single End reads file...")

            # Download reads Libs to FASTQ files
            input_fwd_file_path = readsLibrary['files'][input_params['input_reads_ref']]['files']['fwd']
            sequencing_tech     = readsLibrary['files'][input_params['input_reads_ref']]['sequencing_tech']


            # Run Trimmomatic
            #
            self.log(console, 'Starting Trimmomatic')
            input_fwd_file_path = re.sub ("\.fq$", "", input_fwd_file_path)
            input_fwd_file_path = re.sub ("\.FQ$", "", input_fwd_file_path)
            input_fwd_file_path = re.sub ("\.fastq$", "", input_fwd_file_path)
            input_fwd_file_path = re.sub ("\.FASTQ$", "", input_fwd_file_path)
            output_fwd_file_path = input_fwd_file_path+"_trimm_fwd.fastq"
            input_fwd_file_path  = input_fwd_file_path+".fastq"

            cmdstring = " ".join( (self.TRIMMOMATIC, trimmomatic_options,
                            input_fwd_file_path,
                            output_fwd_file_path,
                            trimmomatic_params) )

            cmdProcess = subprocess.Popen(cmdstring, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

            #report += "cmdstring: " + cmdstring

            outputlines = []
            while True:
                line = cmdProcess.stdout.readline()
                outputlines.append(line)
                if not line: break
                self.log(console, line.replace('\n', ''))

            cmdProcess.stdout.close()
            cmdProcess.wait()
            self.log(console, 'return code: ' + str(cmdProcess.returncode) + '\n')
            if cmdProcess.returncode != 0:
                raise ValueError('Error running kb_trimmomatic, return code: ' +
                                 str(cmdProcess.returncode) + '\n')


            report += "\n".join(outputlines)

            # free up disk
            os.remove(input_fwd_file_path)

            # get read count
            match = re.search(r'Surviving: (\d+)', report)
            readcount = match.group(1)

            # upload reads
            if not os.path.isfile (output_fwd_file_path) \
                or os.path.getsize (output_fwd_file_path) == 0:

                retVal['output_filtered_ref'] = None
            else:
                output_obj_name = input_params['output_reads_name']
                self.log(console, 'Uploading trimmed reads: '+output_obj_name)

                retVal['output_filtered_ref'] = readsUtils_Client.upload_reads ({ 'wsname': str(input_params['output_ws']),
                                                                                  'name': output_obj_name,
                                                                                  # remove sequencing_tech arg once ReadsUtils is updated to accept source_reads_ref
                                                                                  #'sequencing_tech': sequencing_tech,
                                                                                  'source_reads_ref': input_params['input_reads_ref'],
                                                                                  'fwd_file': output_fwd_file_path
                                                                                  })['obj_ref']

                # free up disk
                os.remove(output_fwd_file_path)


        # return created objects
        #
        output = { 'report': report,
                   'output_filtered_ref': retVal['output_filtered_ref'],
                   'output_unpaired_fwd_ref': retVal['output_unpaired_fwd_ref'],
                   'output_unpaired_rev_ref': retVal['output_unpaired_rev_ref']
                 }
        #END execTrimmomaticSingleLibrary

        # At some point might do deeper type checking...
        if not isinstance(output, dict):
            raise ValueError('Method execTrimmomaticSingleLibrary return value ' +
                             'output is not type dict as required.')
        # return the results
        return [output]
    def status(self, ctx):
        #BEGIN_STATUS
        returnVal = {'state': "OK", 'message': "", 'version': self.VERSION,
                     'git_url': self.GIT_URL, 'git_commit_hash': self.GIT_COMMIT_HASH}
        #END_STATUS
        return [returnVal]
