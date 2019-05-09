import yaml
import sys
import argparse
import json
import boto3
import botocore
import time
import subprocess


def create_stack_sets(stacks, stackset_region):
    CF = boto3.client("cloudformation", region_name=stackset_region)
    for stack in stacks:
        stack_name = stack['name']
        stack_description = stack['description']
        with open(stack['template_file'], "r") as file_template:
            with open(stack['parameter_file'], "r") as file_param:
                json_param_file = json.load(file_param)
                try:
                    response = CF.describe_stack_set(
                        StackSetName=stack_name
                    )
                    print("Stack found: {}".format(stack_name))
                    print("Updating...")
                    update_stack = CF.update_stack_set(
                        StackSetName=stack_name,
                        Description=stack_description,
                        TemplateBody=file_template.read(),
                        Parameters=json_param_file,
                        Capabilities=['CAPABILITY_NAMED_IAM']
                        )
                    print("Response: {}".format(update_stack))
                except Exception as e:
                    if e.response['Error']['Code'] == "StackSetNotFoundException":
                        print("Stack NOT found: {}".format(stack_name))
                        print("Creating...")
                        create_stack = CF.create_stack_set(
                            StackSetName=stack_name,
                            Description=stack_description,
                            TemplateBody=file_template.read(),
                            Parameters=json_param_file,
                            Capabilities=['CAPABILITY_NAMED_IAM']
                            )
                        print("Response: {}".format(create_stack))
                    else:
                        print("ERROR: {}".format(e.response['Error']['Code']))
    return "success"


def validate_cfn_nag(stacks, staging_account, staging_region, stackset_region):
    error_count = 0
    for stack in stacks:
        # Parameter validation removed as cfn-nag does not work well with it
        result = subprocess.run(['cfn_nag_scan', '-i', stack['template_file'],
                      '-a', stack['parameter_file']], stdout=subprocess.PIPE)
        # result = subprocess.run(['cfn_nag_scan', '-i', stack['template_file']],
        #                         stdout=subprocess.PIPE)
        print(result.stdout.decode('utf-8'))
        error_count += result.returncode
    if error_count > 0:
        print("Failed one or more validation")
        sys.exit(1)


def validate_cucumber(stacks, staging_account, staging_region, stackset_region):
    error_count = 0
    for stack in stacks:
        try:
            feature_file = stack['feature_test']
            feature_file = feature_file[6::]
            print(feature_file)
            print("Test case found for stack: {}".format(stack['name']))
            try:
                result = subprocess.run(['node_modules/.bin/cucumber-js',
                                        feature_file], stdout=subprocess.PIPE)
                print(result.stdout.decode('utf-8'))
            except Exception as e:
                print(e)
                pass
            error_count += result.returncode
        except Exception as e:
            print("Test case NOT found for stack: {}".format(stack['name']))
            print(e)
            pass
    if error_count > 0:
        print("Failed one or more validation")
        sys.exit(1)


def deploy_to_staging(stacks, staging_account, staging_region, stackset_region):
    operation_ids = {}
    for stack in stacks:
        response = create_stackset_instance(
            stack['name'],
            staging_account,
            staging_region,
            stackset_region
            )
        operation_ids[response] = stack['name']
    monitor_operations(operation_ids, stackset_region)


def deploy_to_production(stacks, stackset_region):
    operation_ids = {}
    for stack in stacks:
        response = create_stackset_instance(
            stack['name'],
            stack['accounts'],
            stack['regions'],
            stackset_region)
        operation_ids[response] = stack['name']
    monitor_operations(operation_ids, stackset_region)


def monitor_operations(operation_ids, stackset_region):
    CF = boto3.client("cloudformation", region_name=stackset_region)
    for operation_id, stackset_name in operation_ids.items():
        error = 0
        success = 0
        while not error < 1 or success < 1:
            response = CF.describe_stack_set_operation(
                StackSetName=stackset_name,
                OperationId=operation_id
            )
            status = response["StackSetOperation"]["Status"]
            if status != 'RUNNING' and status != 'SUCCEEDED':
                error += 1
                print("FAILED - Stackeset: {} Status: {} Operation ID: {}".format(
                    stackset_name, status, operation_id))
            elif status != 'RUNNING' and status == 'SUCCEEDED':
                success += 1
                print("SUCCESS - Stackeset: {} Status: {} Operation ID: {}".format(
                    stackset_name, status, operation_id))
            else:
                pass
            time.sleep(5)
        if error > 0:
            sys.exit(1)
        else:
            pass


def create_stackset_instance(stack_name, accounts, regions, stackset_region):
    CF = boto3.client("cloudformation", region_name=stackset_region)
    if not isinstance(accounts, (list)):
        accounts = [accounts]
    if not isinstance(regions, (list)):
        regions = [regions]
    response = CF.create_stack_instances(
        StackSetName=stack_name,
        Accounts=accounts,
        Regions=regions
    )
    return response['OperationId']


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--file', action='store', dest='name',
                        help='Manifest file name', required=True)
    parser.add_argument('-p', '--phase', action='store', dest='phase',
                        help='Deployment Phase', required=True)
    args = parser.parse_args()
    data = yaml.load(open(args.name))
    staging_account = data['staging_account']
    staging_region = data['staging_region']
    stackset_region = data['stackset_region']

    if args.phase == "stackset":
        print("Phase - Create StackSet")
        create_stack_sets(data['stacks'], stackset_region)
    elif args.phase == "staging":
        print("Phase - Deploy to Staging")
        deploy_to_staging(
            data['stacks'],
            staging_account,
            staging_region,
            stackset_region
            )
    elif args.phase == "production":
        print("Phase - Deploy to Production")
        deploy_to_production(data['stacks'], stackset_region)
    elif args.phase == "cfn-nag":
        print("Phase - cfn-nag")
        validate_cfn_nag(
            data['stacks'],
            staging_account,
            staging_region,
            stackset_region
            )
    elif args.phase == "cucumber":
        print("Phase - Cucumber")
        validate_cucumber(
            data['stacks'],
            staging_account,
            staging_region,
            stackset_region
            )
    else:
        print("Phase not found, try stackset|staging|production|cucumber")


main(sys.argv[1:])
