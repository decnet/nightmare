#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Nightmare Fuzzing Project generic test case minimizer
@author: joxean

@description: This generic test case minimizer, as of 9 of May of 2014, 
only works with Charlie Miller mutated test cases as it doesn't perform
any diffing by itself but, rather, reads the .diff files generated by
the mutator.

The algorithm is as simple as this:

 1) Read the positions from the .diff file where changes were made.
 2) Read the modified bytes at those positions.
 3) Read the whole template file.
 4) Apply only one (byte) change at a time and check for a crash.
 5) If applying only one byte change doesn't work, consider that the 1st
   change applied to the file is mandatory. Apply it to the internally
   read template buffer and remove from the list of changes to check.
 6) Go back to 4.

In the future, the algorithm may be changed adding the following steps:

 * If a crashing change was found after applying a number of other small
   changes before try minimizing it even more by undoing the previously
   applied small patches.
   
Or the following "new" algorithm:

 * Start with all the changes applied. Remove one-per-one all of them
   until the process doesn't crash any more.

This generic test case minimizer was written for Linux/Unix platforms,
I don't think it works as is in Windows as it simply uses the return
codes instead of a debugging interface (because it's easier and less
problematic over all).

"""

import os
import sys
import shutil
import tempfile
import ConfigParser

from hashlib import sha1

script_path = os.path.dirname(os.path.realpath(__file__))
tmp_path = os.path.join(script_path, "..")
sys.path.append(tmp_path)
tmp_path = os.path.join(tmp_path, "runtime")
sys.path.append(tmp_path)

from nfp_log import log
from nfp_process import TimeoutCommand, RETURN_SIGNALS

#-----------------------------------------------------------------------
class CGenericMinimizer:
  def __init__(self, cfg, section):
    self.cfg = cfg
    self.section = section
    self.read_configuration()

    self.diff = []
    self.template = []
    self.crash = {}

  def read_diff(self, diff):
    with open(diff, "rb") as f:
      for line in f.readlines():
        # Ignore lines with comments
        if line.startswith("#"):
          continue
        line = line.strip("\n").strip("\r")
        if line.isdigit():
          self.diff.append(int(line))

  def read_template(self, template):
    self.template = bytearray(open(template, "rb").read())
  
  def read_crash(self, crash):
    tmp = bytearray(open(crash, "rb").read())
    self.crash = {}
    
    for pos in self.diff:
      self.crash[pos] = tmp[pos]

  def read_configuration(self):
    if not os.path.exists(self.cfg):
      raise Exception("Invalid configuration file given")

    parser = ConfigParser.SafeConfigParser()
    parser.optionxform = str
    parser.read(self.cfg)

    if self.section not in parser.sections():
      raise Exception("Section %s does not exists in the given configuration file" % self.section)

    try:
      self.pre_command = parser.get(self.section, 'pre-command')
    except:
      # Ignore it, it isn't mandatory
      self.pre_command = None

    try:
      self.post_command = parser.get(self.section, 'post-command')
    except:
      # Ignore it, it isn't mandatory
      self.post_command = None

    try:
      self.command = parser.get(self.section, 'command')
    except:
      raise Exception("No command specified in the configuration file for section %s" % self.section)
    
    try:
      self.extension = parser.get(self.section, 'extension')
    except:
      raise Exception("No extension specified in the configuration file for section %s" % self.section)

    try:
      self.timeout = parser.get(self.section, 'timeout')
    except:
      # Default timeout is 90 seconds
      self.timeout = 90    
    self.timeout = int(self.timeout)

    try:
      environment = parser.get(self.section, 'environment')
      self.env = dict(parser.items(environment))
    except:
      self.env = {}
    
    try:
      self.cleanup = parser.get(self.section, 'cleanup-command')
    except:
      self.cleanup = None

  def minimize(self, template, crash, diff, outdir):
    self.read_diff(diff)
    self.read_template(template)
    self.read_crash(crash)

    log("Performing test case minimization with a total of %d change(s)" % len(self.diff))
    start_at = os.getenv("NIGHTMARE_ITERATION")
    if start_at is not None:
      start_at = int(start_at)
      log("Starting from iteration %d\n" % start_at)
    else:
      start_at = 0

    self.do_try(outdir, start_at)
  
  def do_try(self, outdir, start_at=0):
    # Try to minimize to just one change
    current_change = 0
    minimized = False
    iteration = 0
    for i in range(len(self.diff)):
      for pos in self.diff:
        if start_at <= iteration:
          log("Minimizing, iteration %d (Max. %d)..." % (iteration, (len(self.diff)) * len(self.diff)))
          temp_file = tempfile.mktemp()
          buf = bytearray(self.template)
          if pos not in self.crash:
            continue
          
          buf[pos] = self.crash[pos]

          with open(temp_file, "wb") as f:
            f.write(buf)

          try:
            for key in self.env:
              os.putenv(key, self.env[key])

            cmd = "%s %s" % (self.command, temp_file)
            cmd_obj = TimeoutCommand(cmd)
            ret = cmd_obj.run(timeout=self.timeout)

            if ret in RETURN_SIGNALS:
              log("Successfully minimized, caught signal %d (%s)!" % (ret, RETURN_SIGNALS[ret]))
              filename = sha1(buf).hexdigest()
              filename = os.path.join(outdir, "%s%s" % (filename, self.extension))
              shutil.copy(temp_file, filename)
              log("Minized test case %s written to disk." % filename)
              minimized = True
              break
          finally:
            os.remove(temp_file)

        if minimized:
          break

        iteration += 1

      if minimized:
          break

      value = self.diff.pop()
      if value in self.crash:
        self.template[value] = self.crash[value]
        del self.crash[value]

    if not minimized:
      log("Sorry, could not minimize crashing file!")

#-----------------------------------------------------------------------
def main(cfg, section, template, crash, diff, output):
  minimizer = CGenericMinimizer(cfg, section)
  minimizer.minimize(template, crash, diff, output)

#-----------------------------------------------------------------------
def usage():
  print "Usage:", sys.argv[0], "<config file> <section> <template file> <crashing file> <diff file> <output directory>"

if __name__ == "__main__":
  if len(sys.argv) != 7:
    usage()
  else:
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6])

