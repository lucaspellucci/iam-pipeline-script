# aws-pipeline-scripts

## Usage
python3 deploy.py -f <path/to/manifest/file> -p (cfn-nag|stackset|staging|production)

## Stages

cfn-nag - Runs cfn-nag against the templates described in the Manifest File.

stackset - Creates the stacksets for the stacks described in the Manifest file.

staging - Creates the stackset instance in the staging account.

production -  Creates the stackset instance in the prodcution accounts.
