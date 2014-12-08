notss-eh
========
###### _A Not So Simple Event-Handler for Nagios_

Overview
========
The notss-eh script is a flexible event-handler for Nagios-compatible monitoring systems.
It's designed to keep execution logic and action execution separate - this gives you the option to use different "execution modules" or add your own.

Currently it only supports executing "NRPE commands", but more modules are planned like SSH, SNMP sets, VMWare commands and similar!

Features
========
- Action execution on specified check attempt or soft state changes
- Merlin check source detection (useful in peered setups)
- Easy to extend with new "execution modules"
- Resonable logging to syslog or stdout
 
Execution modules
=================
- NRPE
  - Executes NRPE commands with the "check_nrpe" plugin
  - Supports result status verification
  - Dependencies: None

Installation and configuration
==============================
The main parts of the script uses nothing outside the Python 2.7 standard library (if you use it on EL7 you might need to install the "argparse" module), but the execution modules might have their own.

Download the "notss-eh.py" and place it in a suitable directory on the monitoring system(s).
Some of the parameters should be set with Nagios macros - below is an example command configuration:

```
# Using notss-eh with source checking to execute NRPE commands without session encryption
command_name: notss-eh-hard_checksrc-nrpe_insecure
command_line: $USER1$/custom/notss-eh.py --host "$HOSTADDRESS$" --name "$HOSTNAME$" --description "$SERVICEDESC$" --state "$SERVICESTATE$" --state-type "$SERVICESTATETYPE$" --attempt "$SERVICEATTEMPT$" --ok "$ARG1$" --warning "$ARG2$" --critical "$ARG3$" --unknown "$ARG4$" -C -l syslog nrpe --insecure
```

To use it with a service, set the proper arguments for the event handler - you can use the "skip" keyword to ignore action specified states like "OK" or "WARNING".
