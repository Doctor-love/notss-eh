#!/usr/bin/env python

'''notss-eh - A not so simple eventhandler for Nagios.

Supports executing "actions" like NRPE commands - hopefully more in the future.
Built and tested for use on RHEL 6 with op5 Monitor 7.0.2'''

prog = 'notss-eh'
version = '0.9.1'

try:
    import argparse
    import logging
    import logging.handlers
    import subprocess
    import datetime
    import getpass
    import random
    import time
    import os

except ImportError as excp:
    print 'Error - could not import all required Python modules:\n"%s"' % excp
    exit(2)
    
logger = logging.getLogger('notss-eh')


# Parses command line arguments
def aparser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog='Written by Joel Rangsmo <joel@rangsmo.se>',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # Common phrases in help text
    skip = '(use "skip" keyword to ignore action)'

    # Main arguments
    parser.add_argument(
        '-H', '--host', help='Specify host address', required=True)

    parser.add_argument(
        '-n', '--name', help='Specify host name', required=True)

    parser.add_argument('-d', '--description',
                        help='Specify service description', required=True)

    parser.add_argument('-s', '--state', help='Current state',
                        choices=('OK', 'WARNING', 'CRITICAL', 'UNKNOWN'),
                        required=True)

    parser.add_argument('-t', '--state-type', help='State type',
                        choices=('SOFT', 'HARD'), required=True)

    parser.add_argument('-a', '--attempt',
                        help='Specify check attempt',
                        type=int, required=True)

    parser.add_argument(
        '-o', '--ok', help='Action(s) executing on OK',
        action='append')

    parser.add_argument(
        '-w', '--warning', help='Action(s) executing on WARNING %s' % skip,
        action='append')

    parser.add_argument(
        '-c', '--critical', help='Action(s) executing on CRITICAL %s' % skip,
        action='append')

    parser.add_argument(
        '-u', '--unknown', help='Action(s) executing on UNKNOWN %s' % skip,
        action='append')

    softexec = parser.add_mutually_exclusive_group()

    softexec.add_argument('-S', '--soft',
                          help='Execute action(s) on soft state changes',
                          action='store_true', default=False)

    softexec.add_argument('-A', '--attempt-exec',
                          help='Execute action(s) on specified check attempt',
                          type=int)

    parser.add_argument(
        '-W', '--wait',
        help='Specifies seconds to sleep between execution of actions)',
        type=int)

    parser.add_argument(
        '-C', '--checksrc',
        help='Enables a hack to determine if this host  is the check source ' +
        'for the service (Can be usefull in peered setups)',
        action='store_true', default=False)

    # General settings
    parser.add_argument('-l', '--logging', help='Set logging destination',
                        choices=('stream', 'syslog', 'none'),
                        default='stream')

    parser.add_argument('-V', '--verbose', help='Enable verbose logging',
                        action='store_true', default=False)

    parser.add_argument('-v', '--version', help='Display program version',
                        action='version', version=version)

    parser.add_argument('--funk', help=argparse.SUPPRESS,
                        action='store_true', default=False)

    # Sub-parsers for execution modules
    mod = parser.add_subparsers(
        help='Specifies action execution module', dest='execmod')

    # --------------------------------------------------------------------------
    # Sub-parser for NRPE execution module
    mod_nrpe = mod.add_parser(
        'nrpe', help='Executes command(s) with NRPE queries')

    mod_nrpe.add_argument('-H', '--host',
                          dest='mod_host',
                          help='Specify optional remote host for execution')

    mod_nrpe.add_argument('-p', '--nrpe-plugin',
                          dest='mod_nrpe_plugin',
                          help='Location of "check_nrpe" executable',
                          default='/opt/plugins/check_nrpe')

    mod_nrpe.add_argument('-i', '--insecure',
                          dest='mod_insecure',
                          help='Disable encryption for connection',
                          action='store_true', default=False)

    mod_nrpe.add_argument(
        '-I', '--ignore', dest='mod_ignore',
        help='Ignore NRPE status output' +
        '(can be useful if the triggered plugin does not return any)',
        action='store_true', default=False)

    # --------------------------------------------------------------------------
    # Sub-parser for SSH execution module
    mod_ssh = mod.add_parser(
        'ssh', help='Executes command(s) with SSH')

    mod_ssh.add_argument('-u', '--user',
                         dest='mod_user',
                         help='Username on remote host',
                         required=True)

    mod_ssh.add_argument('-H', '--host',
                         dest='mod_host',
                         help='Specify optional remote host for execution')

    mod_ssh.add_argument('-p', '--port',
                         dest='mod_port',
                         help='SSH port on remote host',
                         type=int, default=22)

    # Allows the user to specify a password or private key for authentication
    mod_ssh_auth = mod_ssh.add_mutually_exclusive_group(required=True)

    mod_ssh_auth.add_argument(
        '-k', '--private-key',
        dest='mod_key',
        help='OpenSSH compatible private key file for authentication')

    mod_ssh_auth.add_argument(
        '-P', '--password',
        dest='mod_password',
        help='Password for authentication (not recommended)')

    # Allows the user to specify know host file or trust all host keys
    mod_ssh_keypol = mod_ssh.add_mutually_exclusive_group(required=True)

    mod_ssh_keypol.add_argument(
        '-K', '--known-hosts',
        dest='mod_known',
        help='OpenSSH compatible known hosts file for host key verification')

    mod_ssh_keypol.add_argument(
        '-i', '--insecure',
        dest='mod_insecure',
        help='Automatically trust host key (not recommended)',
        action='store_true', default=False)

    # --------------------------------------------------------------------------
    # Sub-parser for shell execution module
    mod_shell = mod.add_parser(
        'shell', help='Executes local shell command(s)')

    mod_shell.add_argument(
        '-s', '--shell', dest='mod_shell_shell',
        help='Specifies system shell',
        choices=('/bin/sh', '/bin/bash', '/usr/local/bin/bash'),
        default='/bin/sh')

    mod_shell.add_argument(
        '-r', '--returncode', dest='mod_shell_retcode',
        help='Specify return code to verify successful execution of commands',
        type=int)

    mod_shell.add_argument(
        '-m', '--mute', dest='mod_shell_mute',
        help='Mute the output of the shell command',
        action='store_true', default=False)

    # --------------------------------------------------------------------------
    return parser.parse_args()


# Configures application logging
def logsetup(destination, verbose):
    logger = logging.getLogger('notss-eh')
    formatter = logging.Formatter(
        'notss-eh: %(levelname)s - %(message)s')

    if verbose:
        logger.setLevel(logging.DEBUG)

    else:
        logger.setLevel(logging.INFO)

    if destination == 'stream':
        loghandler = logging.StreamHandler()

    elif destination == 'syslog':
        loghandler = logging.handlers.SysLogHandler(address='/dev/log')

    elif destination == 'none':
        loghandler = logging.NullHandler()

    loghandler.setFormatter(formatter)
    logger.addHandler(loghandler)

    return logger


# Non important function to generate data output
def nothingtoseehere():
    print '''
                      |
                      |            .'
                  \   |   /
               `.  .d88b.   .'
                  d888888b
      --     --  (88888888)  --
                  Y888888Y
              .'   `Y88Y'   `.
                  /
           .'         !        `.


       .,,-~&,               ,~"~.
      { /___/\`.             > ::::
     { `}'~.~/\ \   ` `     <, ?::;
     {`}'\._/  ) }   ) )     l_  f
      ,__/ l_,'-/  .'.'    ,__}--{_.
     {  `.__.' (          /         }
      \ \    )  )        /          !
       \-\`-'`-'        /  ,    1  J;
  ` `   \ \___l,-_,___.'  /1    !  Y
   ) )   k____-~'-l_____.' |    l /
 .'.'   /===#==\           l     f
      .'        `.         I===I=I
    ,' ,'       `.`.       f     }
  ,' ,'  /      \ `.`.     |     }
.'^.^.^.'`.'`.^.'`.'`.^.   l    Y;
           `.   \          }    |
            !`,  \         |    |
            l /   }       ,1    |
            l/   /        !l   ,l
            /  ,'         ! \    \\
'''

    if datetime.date.today().weekday() == 4:
        tunes = [
            {'titel': 'Bruce Hornsby & the Range - The Way It Is',
             'url': 'http://youtu.be/4-k2JCV4TCs'},
            {'titel': '2 Unlimited - No Limit',
             'url': 'http://youtu.be/RkEXGgdqMz8'}]

    else:
        tunes = [
            {'titel': 'Kool & The Gang - Get Down On It ',
             'url': 'http://youtu.be/qchPLaiKocI'},
            {'titel': 'Chic - Everybody Dance',
             'url': 'http://youtu.be/J1MMzMGX8xY'},
            {'titel': 'Boney M - Rasputin',
             'url': 'http://youtu.be/9_T3x8qBoic'},
            {'titel': 'Jamiroquai - Cosmic Girl',
             'url': 'http://youtu.be/D-NvQ6VJYtE'}]

    tune = tunes[random.randrange(0, len(tunes))]

    print ('Millitaa [SC]haniqua calls for party time, fellas!' +
           '\n%s - %s' % (tune['titel'], tune['url']))


# Hack to check if this host is the check source for the object
def checksrc(name, description):
    logger.info(
        'Trying to determine check source for host "%s" and service "%s"'
        % (name, description))

    monpath = '/usr/bin/mon'

    logger.debug(
        'Executing the following mon command to determine the check source: ' +
        '%s query ls services -c check_source host_name ' % monpath +
        '-e "%s" description -e "%s"' % (name, description))

    command = subprocess.Popen(
        '%s query ls services -c check_source ' % monpath +
        'host_name -e "%s" description -e "%s"' % (name, description),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

    command.wait()
    source = command.communicate()

    if command.returncode != 0:
        logger.error('Failed to run "mon" command!')
        logger.debug('Communicate: \n\n"%s" -\n\nReturn code: "%i"'
                     % (str(source), command.returncode))

        return False

    elif 'Core Worker' in source[0]:
        logger.info('This host was found as the check source')

        return True

    elif not source[0].replace('\n', ''):
        logger.info('Could not find source for service "%s"' % description)
        logger.debug('Communicate: \n\n"%s"' % str(source))

    else:
        logger.info('This host was not found to be the check source')
        logger.debug('Communicate: \n\n"%s"' % str(source))

        return False

    logger.info('Looking for check source for host "%s"' % name)

    logger.debug(
        'Executing the following mon command to determine the check source: ' +
        '%s query ls hosts -c check_source name -e "%s"'
        % (monpath, name))

    command = subprocess.Popen(
        '%s query ls hosts -c check_source name -e "%s"'
        % (monpath, name),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

    command.wait()
    source = command.communicate()

    if command.returncode != 0:
        logger.error('Failed to run "mon" command!')
        logger.debug('Communicate: \n\n"%s" -\n\nReturn code: "%i"'
                     % (str(source), command.returncode))

        return False

    elif 'Core Worker' in source[0]:
        logger.info('This host was found as the check source')

        return True

    elif not source[0].replace('\n', ''):
        logger.info('Could not find source for host "%s"' % name)
        logger.debug('Communicate: \n\n"%s"' % str(source))

        return False

    else:
        logger.info('This host was not found to be the check source')
        logger.debug('Communicate: \n\n"%s"' % str(source))

        return False


# Checks which, if any, actions should be executed
def execactions(state, state_type, attempt, soft, attempt_exec):
    logger.info('Checking if any actions should be added to execution list')

    if soft:
        logger.info('Adding "%s" actions to execution list ' % state +
                    'since soft state execution is enabled')

    elif attempt_exec and attempt_exec == attempt:
        logger.info('Adding "%s" actions to execution list ' % state +
                    'since check attempt matches attempt execution number')

    elif attempt_exec and attempt_exec != attempt:
        logger.info('Adding no actions to execution list since check attempt' +
                    ' did not match check attempt execution number')

        return False

    elif state_type == 'HARD':
        logger.info('Adding "%s" actions to execution list ' % state +
                    'since the state is hard')

    else:
        logger.info('Adding no actions to execution ' +
                    'list since the state change was soft')

        return False

    return state


# Execution module for NRPE commands
def execmod_nrpe(actions, wait, host, mod_host, nrpe_plugin, insecure, ignore):
    if mod_host:
        logger.debug('A seperate execution host has been specified')

        host = mod_host

    logger.info('Running NRPE commands on host "%s"' % host)

    if insecure:
        logger.info('NRPE session encryption has been disabled')

    if insecure:
        logger.info('NRPE session encryption has been disabled')

    if ignore:
        logger.info('NRPE status output checking has been disabled')

    # Checking if the "check_nrpe" plugin can be found
    if not os.path.isfile(nrpe_plugin):
        logger.error('Could not find the NRPE plugin at "%s"' % nrpe_plugin)

        return False

    # Running all commands in actions
    for command in actions:
        logger.info('Running NRPE command "%s"' % command)

        if wait:
            logger.debug(
                'Waiting %i second(s) before command execution' % wait)

            time.sleep(wait)

        if insecure:
            result = subprocess.Popen(
                '%s -H %s -c %s' % (nrpe_plugin, host, command),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

        else:
            result = subprocess.Popen(
                '%s -H %s -n -c %s' % (nrpe_plugin, host, command),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)

        result.wait()

        if ignore:
            logger.debug(
                'Ignoring NRPE command output - ' +
                'Communicate:\n\n"%s"\n\nStatus code: %i'
                % (str(result.communicate()), result.returncode))

            continue

        if result.returncode != 0:
            logger.error('Error occured while executing NRPE command: "%s"'
                         % str(result.communicate()))

        else:
            logger.info('Command execution successful - output: "%s"'
                        % result.communicate()[0].strip())

    # Returning to main function does not do much ATM
    return True


# Execution module for SSH commands
def execmod_ssh(actions, wait, host, user, mod_host,
                port, key, password, known, insecure):

    # Trying to import the Python SSH module
    try:
        import paramiko

    except ImportError:
        logger.error(
            'Falied to import the Paramiko SSH module - exiting')

        return False

    if mod_host:
        logger.debug('A seperate execution host has been specified')

        host = mod_host

    logger.info(
        'Running SSH command(s) on host "%s:%i" as user "%s"'
        % (host, port, user))

    if key:
        logger.info('Using private key for user authentication')

    else:
        logger.info('Using password for user authentication')

    session = paramiko.SSHClient()

    # Disables host key verification for SSH session
    if insecure:
        logger.info('SSH host key verification has been disabled')
        session.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    else:
        logger.debug('Loading known hosts file from "%s"' % known)

        try:
            session.load_host_keys(known)

        except IOError as emsg:
            logger.error(
                'Failed to load known hosts file: "%s"' % emsg)

            return False

    try:
        session.connect(
            host, username=user, port=port,
            key_filename=key, password=password)

        for action in actions:
            if wait:
                logger.debug(
                    'Waiting %i second(s) before command execution' % wait)

                time.sleep(wait)

            logger.info('Executing command "%s" over SSH' % action)

            stdin, stdout, stderr = session.exec_command(action)
            stdin.close()

            stdout = stdout.read()
            stderr = stderr.read()

            logger.info(
                'Output of command "%s" - stdout: "%s", stderr: "%s"'
                % (action, str(stdout).strip(), str(stderr).strip()))

    except paramiko.SSHException as emsg:
        logger.error('Failed to connect to host "%s": "%s"' % (host, emsg))

        return False

    session.close()

    # Returning to main function does not do much ATM
    return True


# Execution module for local system shell commands
def execmod_shell(actions, wait, shell, returncode, mute):
    logger.info(
        'Executing %i commands with shell "%s"'
        % (len(actions), shell))

    if mute:
        logger.debug('Shell command output muting is enabled')

    if returncode or returncode == 0:
        logger.debug(
            'Verifying success of command execution with return code %i'
            % returncode)

    else:
        logger.debug('Command execution result checking is disabled')

    for action in actions:
        if wait:
            logger.debug(
                'Waiting %i second(s) before command execution' % wait)

            time.sleep(wait)

        logger.info('Executing shell command "%s"' % action)

        command = subprocess.Popen(
            '%s' % action,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=shell)

        command.wait()
        output = command.communicate()

        if not mute:
            logger.info(
                'Output of shell of command "%s":\nstdout: "%s"'
                % (action, str(output[0]).strip()) +
                '\nstderr: "%s"' % str(output[1]).strip())

        if returncode is False:
            continue

        logger.debug('Checking return code for command "%s"' % action)

        if command.returncode == returncode:
            logger.info(
                'Command "%s" executed successfully ' % action +
                '(return code %i was matched)' % returncode)

        else:
            logger.error(
                'Command "%s" did not execute successfully ' % action +
                '(return code %i was not matched)' % returncode)

    # Returning to main function does not do much ATM
    return True


# Main function
def main():
    # Parses command line arguments
    args = aparser()

    # Non important function to generate data output
    if args.funk:
        nothingtoseehere()
        exit(3)

    # Configures application logging
    global logger
    logger = logsetup(args.logging, args.verbose)

    logger.debug('Provided arguments: "%s"' % args)

    logger.info(
        'The event-handler has been started by user "%s"' % getpass.getuser() +
        ' for host "%s" and service "%s". ' % (args.name, args.description))

    # Hack to check if this host is the check source for the service
    if args.checksrc and not checksrc(args.name, args.description):
        exit(0)

    # Checks if actions should be executed and add them to the "actions" array
    actions = execactions(args.state, args.state_type,
                          args.attempt, args.soft, args.attempt_exec)

    if actions == 'OK':
        actions = args.ok

    elif actions == 'WARNING':
        actions = args.warning

    elif actions == 'CRITICAL':
        actions = args.critical

    elif actions == 'UNKNOWN':
        actions = args.unknown

    else:
        exit(0)

    if not actions or actions[0].lower() == 'skip':
        logger.info('No actions for state "%s" has been provided' % args.state)
        exit(0)

    else:
        logger.info('Added %i action(s) to execution list' % len(actions))

    logger.debug('Actions for execution: "%s"' % actions)

    # "Router" for execution module selection
    if args.execmod == 'nrpe':
        execmod_nrpe(
            actions, args.wait, args.host,
            args.mod_host, args.mod_nrpe_plugin,
            args.mod_insecure, args.mod_ignore)

    elif args.execmod == 'ssh':
        execmod_ssh(
            actions, args.wait, args.host,
            args.mod_user, args.mod_host, args.mod_port,
            args.mod_key, args.mod_password, args.mod_known, args.mod_insecure)

    elif args.execmod == 'shell':
        execmod_shell(
            actions, args.wait, args.mod_shell_shell,
            args.mod_shell_retcode, args.mod_shell_mute)

    else:
        logger.error('Could not find execution module for "%s"' % args.execmod)
        exit(2)


# Runs main if script is being used stand alone
if __name__ == '__main__':
    main()
