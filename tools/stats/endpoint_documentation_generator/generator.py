import json
import urllib.parse
from datetime import datetime

from .template import endpoint_documentation_template, data_set_template, parameter_line_template, parameter_pattern_template

from tools.library.functions import get_python_variable_name
from tools.library.file_handler import save_file, get_file_path
from tools.stats.endpoint_analysis.analysis import load_endpoint_file, default_value_for_valid_response
from tools.stats.library.mapping import endpoint_list, parameter_map, parameter_variations


def get_endpoint_query_string_parameters(parameters, nullable_parameters, parameter_patterns):
    params = {}
    for parameter in parameters:
        if parameter in nullable_parameters:
            value = ''
        elif parameter in default_value_for_valid_response:
            value = default_value_for_valid_response[parameter]
        else:
            map_key = 'non-nullable'
            pattern_key = parameter_map[parameter][map_key][parameter_patterns[parameter]]
            value = parameter_variations[pattern_key]['parameter_value']
        params[parameter] = value
    valid_url = urllib.parse.urlencode(params)
    return valid_url


def get_endpoint_documentation(endpoint, endpoints_information):
    endpoint_analysis = endpoints_information[endpoint]
    parameters = endpoint_analysis['parameters']
    parameters.sort()
    required_parameters = endpoint_analysis['required_parameters']
    nullable_parameters = endpoint_analysis['nullable_parameters']
    parameter_patterns = endpoint_analysis['parameter_patterns']
    data_sets = endpoint_analysis['data_sets']

    query_string_parameters = get_endpoint_query_string_parameters(parameters=parameters,
                                                                   nullable_parameters=nullable_parameters,
                                                                   parameter_patterns=parameter_patterns)

    data_set_texts = []
    for data_set_name, columns in data_sets.items():
        method_name = get_python_variable_name(data_set_name)
        data_set_text = data_set_template.format(data_set_name=data_set_name, columns=str(columns),
                                                 method_name=method_name)
        data_set_texts.append(data_set_text)

    parameter_texts = []
    parameter_pattern_texts = []
    for parameter in reversed(parameters):
        pattern = ''
        if parameter_patterns[parameter]:
            pattern = "`{parameter_pattern}`".format(parameter_pattern=parameter_patterns[parameter]
                                                     .replace('|', r'\|'))
        required = ''
        nullable = ''
        map_key = 'non-nullable'
        if parameter in required_parameters:
            required = '`Y`'
        if parameter in nullable_parameters:
            nullable = '`Y`'
            map_key = 'nullable'

        parameter_mapping_class = parameter_map[parameter][map_key][parameter_patterns[parameter]]
        default_value = parameter_variations[parameter_mapping_class]['parameter_value']
        python_parameter_variable = get_python_variable_name(parameter_mapping_class)

        parameter_line = parameter_line_template.format(api_parameter_name=parameter,
                                                        python_parameter_variable=python_parameter_variable,
                                                        default_value=default_value,
                                                        required=required, nullable=nullable)

        if parameter in nullable_parameters:
            parameter_texts.append(parameter_line)
            # Maintain same order as parameters table but do not show when parameter has no pattern.
            if pattern:
                parameter_pattern_texts.append(parameter_pattern_template.format(api_parameter_name=parameter,
                                                                                 parameter_pattern=pattern))
        else:
            parameter_texts.insert(0, parameter_line)
            if pattern:
                parameter_pattern_texts.insert(0, parameter_pattern_template.format(api_parameter_name=parameter,
                                                                                    parameter_pattern=pattern))

    json_text = json.dumps(endpoint_analysis, sort_keys=True, indent=4)

    documentation_text = endpoint_documentation_template.format(endpoint=endpoint, endpoint__lowercase=endpoint.lower(),
                                                                query_string_parameters=query_string_parameters,
                                                                json=json_text,
                                                                parameters='\n'.join(parameter_texts),
                                                                parameter_patterns='\n'.join(parameter_pattern_texts),
                                                                data_sets='\n'.join(data_set_texts),
                                                                validated_date=datetime.now().date())

    return documentation_text


def generate_all_endpoint_documentation(directory='endpoint_documentation'):
    endpoints_information = load_endpoint_file()
    for endpoint in endpoint_list:
        if endpoints_information[endpoint]['status'] != 'success':
            continue
        file_path = get_file_path(directory)
        file_name = '{}.md'.format(endpoint.lower())
        contents = get_endpoint_documentation(endpoint=endpoint, endpoints_information=endpoints_information)
        save_file(file_path=file_path, file_name=file_name, contents=contents)
