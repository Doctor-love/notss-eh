#!/usr/bin/env python

'''notss-eh - A not so simple eventhandler for Nagios.

Supports executing "actions" like NRPE commands - hopefully more in the future.
Built and tested for use on RHEL 6 with op5 Monitor 7.0.2'''

try:
    import argparse
    import logging
    import logging.handlers
    import subprocess
    import datetime
    import getpass
    import random
    import os

except ImportError as excp:
    print 'Error - could not import all required Python modules:\n\n"%s"' % excp
    exit(2)

prog = 'notss-eh'
version = '0.2'


# Parses command line arguments
def aparser():
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog='Written by Joel Rangsmo <joel@rangsmo.se>',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

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
        '-w', '--warning', help='Action(s) executing on WARNING',
        action='append')

    parser.add_argument(
        '-c', '--critical', help='Action(s) executing on CRITICAL',
        action='append')

    parser.add_argument(
        '-u', '--unknown', help='Action(s) executing on UNKNOWN',
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

    mod_nrpe.add_argument('-p', '--nrpe-plugin',
                          help='Location of "check_nrpe" executable',
                          default='/opt/plugins/check_nrpe')

    mod_nrpe.add_argument('-i', '--insecure',
                          help='Disable encryption for connection',
                          action='store_true', default=False)

    mod_nrpe.add_argument(
        '-I', '--ignore',
        help='Ignore NRPE status output' +
        '(can be useful if the triggered plugin does not return any)',
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
    logger = logging.getLogger('notss-eh')

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
    logger = logging.getLogger('notss-eh')

    logger.info('Checking if any actions should be added to execution list')

    if soft:
        logger.info('Adding "%s" actions to execution list ' % state +
                    'since soft state execution is enabled')

    elif attempt_exec and attempt_exec == attempt:
        logger.info('Adding "%s" actions to execution list ' % state +
                    'since check attempt matches attempt execution number')

    elif attempt_exec and attempt_exec != attempt:
        logger.info('Adding no actions to execution list since check attempt ' +
                    'did not match check attempt execution number')

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
def execmod_nrpe(actions, host, nrpe_plugin, insecure, ignore):
    logger = logging.getLogger('notss-eh')

    logger.info('Running NRPE commands on host "%s"' % host)

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


# Main function
def main():
    # Parses command line arguments
    args = aparser()

    # Non important function to generate data output
    if args.funk:
        nothingtoseehere()
        exit(3)

    # Configures application logging
    logsetup(args.logging, args.verbose)
    logger = logging.getLogger('notss-eh')

    logger.debug('Provided arguments: "%s"' % args)
    logger.info(
        'The event-handler has been started by user "%s" ' % getpass.getuser() +
        'for host "%s" and service "%s". ' % (args.name, args.description))

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

    if not actions:
        logger.info('No actions for state "%s" have been provided' % args.state)
        exit(0)

    else:
        logger.info('Added %i action(s) to execution list' % len(actions))

    logger.debug('Actions for execution:\n\n"%s"' % actions)

    # "Router for execution module selection
    if args.execmod == 'nrpe':
        execmod_nrpe(actions, args.host, args.nrpe_plugin,
                     args.insecure, args.ignore)

    else:
        logger.error('Could not find execution module for "%s"' % args.execmod)
        exit(2)


# Runs main if script is being used stand alone
if __name__ == '__main__':
    main()
