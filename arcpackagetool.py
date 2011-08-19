#!/usr/bin/python
#
# This script creates a Mac OS X NorduGrid ARC client package.
# The following environment variables can be used to control the outcome:
# ARC_BUILD_CHANNEL (nightlies, releases, testing, experimental, svn)
# ARC_BUILD_VERSION (e.g. 1970-01-01, 1.0.0...)
# ARC_BUILD_RELEASEVERSION (ARC_BUILD_VERSION)
# ARC_BUILD_MAKECHECK (no, yes)
# ARC_BUILD_INTERACTIVE (no, yes)
# ARC_BUILD_LFC (no, yes)
# ARC_BUILD_CLEANONSUCCESS (yes, no)
#
# TODO:
# - Support building different architectures, currently only x86_64 is
#   supported.
#   ARC_BUILD_ARCHITECTURE (x86_64, i386)


import os, sys, stat
from os.path import join as pj
import tempfile
import shutil
import datetime, time
import subprocess
import urllib
import re
import tarfile
import glob
import gzip


def otool(patterns):
    '''Returns a dictionary with key vs value pairs as files vs list of linked
    libraries.'''
    files = []
    for pattern in patterns:
        files += glob.glob(pattern)
    proc_otool = subprocess.Popen(["otool", "-L"] + files, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    stdout, stderr = proc_otool.communicate()

    paths_links = {}
    current_file = ''
    for line in stdout.splitlines():
        if re.search('is not an object file', line):
            continue
        if line[-1] == ":":
            current_file = line[:-1]
            paths_links[current_file] = []
            continue
        paths_links[current_file].append(line.split()[0])
    return paths_links

def changeinstallnames(pattern, paths):
    linked_libraries = otool([pattern])
    for exec_lib in linked_libraries:
        chginstname_arg = []
        for lib in linked_libraries[exec_lib]:
            for frompath in paths:
                if lib[:len(frompath)] == frompath:
                    chginstname_arg += ["-change", lib, pj(paths[frompath], os.path.basename(lib))]
        chginstname = subprocess.Popen(["install_name_tool", "-id", "@loader_path/"+os.path.basename(exec_lib)] + chginstname_arg + [exec_lib], stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        chginstname.wait()
    return True

def hdiutil(args):
    proc_hdiutil = subprocess.Popen(["hdiutil"] + args, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    stdout, stderr = proc_hdiutil.communicate()
    return { "success" : proc_hdiutil.returncode == 0, "stdout" : stdout, "stderr" : stderr}



class ARCPackageTool:
    ## DEFAULT VALUES.
    name = "nordugrid-arc"

    # Currently only used for naming
    architecture = "x86_64"

    # Where to store ARC globus modules/libraries in order to separate globus dependency. Relative to nordugrid working directory.
    arcglobusdir = "globus/lib"

    # The following packages must be installed before building ARC.
    # Order matters!
    deppackages =  ['pkgconfig', 'libiconv', 'gettext', 'libsigcxx2',
                    'glib2', 'glibmm', 'libtool', 'grid-packaging-tools']

    # The following globus packages are needed by the ARC globus modules.
    # Order matters!
    deppackages += [ 'globus-'+x for x in
                      ['core', 'libtool', 'common', 'callout', 'openssl',
                       'gsi-openssl-error', 'gsi-proxy-ssl', 'openssl-module',
                       'gsi-cert-utils', 'gsi-sysconfig', 'gsi-callback',
                       'gsi-credential', 'gsi-proxy-core', 'gssapi-gsi',
                       'gss-assist', 'gssapi-error', 'xio', 'xio-gsi-driver',
                       'io', 'xio-popen-driver', 'ftp-control', 'ftp-client',
                       'rls-client']
                    ]

    def mypj(self, path1, path2 = '', path3 = '', path4 = ''):
        if path1[:len(self.workdir)] == self.workdir:
            return pj(path1, path2, path3, path4).rstrip('/')
        return pj(self.workdir, path1, path2, path3, path4).rstrip('/')

    def toggleownmacportconf(self, switch):
        if switch:
            if os.path.islink(pj(os.environ['HOME'], '.macports/macports.conf')):
                if os.readlink(pj(os.environ['HOME'], '.macports/macports.conf')) == self.mypj('macports.conf'):
                    return
                os.remove(pj(os.environ['HOME'], '.macports/macports.conf'))
            elif os.path.isfile(pj(os.environ['HOME'], '.macports/macports.conf')):
                os.rename(pj(os.environ['HOME'], '.macports/macports.conf'), self.mypj('macports.conf.orig'))

            os.symlink(self.mypj("macports.conf"), pj(os.environ['HOME'], '.macports/macports.conf'))
        elif os.path.islink(pj(os.environ['HOME'], '.macports/macports.conf')) and \
                 os.readlink(pj(os.environ['HOME'], '.macports/macports.conf')) == self.mypj('macports.conf'):
            os.remove(pj(os.environ['HOME'], '.macports/macports.conf'))
            if os.path.isfile(self.mypj('macports.conf.orig')):
                os.rename(self.mypj('macports.conf.orig'), pj(os.environ['HOME'], '.macports/macports.conf'))

    def port(self, args, useownconf = False, returnoutput = True):
        if useownconf:
            self.toggleownmacportconf(True)

        if returnoutput:
            proc_port = subprocess.Popen(["port"] + args, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
            stdout, stderr = proc_port.communicate()
        else:
            proc_port = subprocess.Popen(["port"] + args)
            proc_port.wait()
            stdout, stderr = '', ''

        if useownconf:
            self.toggleownmacportconf(False)
        return { "success" : proc_port.returncode == 0, "stdout" : stdout, "stderr" : stderr}

    def initialise(self):
        self.workdir = tempfile.mkdtemp('', 'arc-workdir-')

        if not os.path.isdir(pj(os.environ['HOME'], '.macports')):
            os.mkdir(pj(os.environ['HOME'], '.macports'))
        os.mkdir(self.mypj('macports'))
        os.mkdir(self.mypj('macports/registry'))
        os.mkdir(self.mypj('macports/logs'))
        os.mkdir(self.mypj('macports/software'))
        os.mkdir(self.mypj('macports/build'))

        os.symlink('/opt/local/var/macports/sources', self.mypj('macports/sources'))
        shutil.copy2('/opt/local/var/macports/registry/registry.db', self.mypj('macports/registry/registry.db'))
        open(self.mypj('macports/variants.conf'), 'a').close()

        mp_conf = open(self.mypj('macports.conf'), 'w')
        mp_conf.writelines("""# Directory where MacPorts is installed.
prefix           /opt/local
# Where to store MacPorts working data
portdbpath       %(workdir)s/macports
applications_dir /Applications/MacPorts
frameworks_dir   /opt/local/Library/Frameworks
sources_conf     /opt/local/etc/macports/sources.conf
variants_conf    %(workdir)s/macports/variants.conf
binpath          %(workdir)s/install/bin:/opt/local/bin:/opt/local/sbin:/bin:/sbin:/usr/bin:/usr/sbin
universal_archs     x86_64 i386
""" % { 'workdir' : self.workdir})
        mp_conf.close()

        return True

    def requiredpackagescheck(self):
        # The following packages are required to be installed to build the stand-alone package.
        requiredpkgs  = ["gsed", "gperf", "autoconf", "automake", "wget", "doxygen", "p5-archive-tar", "perl5"]
        if self.buildlfc:
            requiredpkgs += ["gsoap", "imake"]
        installedpkgs = [ line.split()[0] for line in self.port(["installed"] + requiredpkgs, True, True)["stdout"].splitlines()[1:] ]

        if set(requiredpkgs)-set(installedpkgs):
            print "The following packages are required to build the stand-alone:"
            print " ".join(set(requiredpkgs)-set(installedpkgs))
            print "Please install them."
            return False

        return True

    def fetchsource(self):
        if not os.path.isdir(self.mypj(self.name)):
            os.mkdir(self.mypj(self.name))

        if (self.buildlfc):
          # To extract the VOMS and LFC source RPMs the rpm2cpio script is needed
          try:
            if os.path.isfile(self.mypj("rpm2cpio.sh")):
              os.remove(self.mypj("rpm2cpio.sh"))
            urllib.urlretrieve("http://svn.nordugrid.org/trac/packaging/export/590/macports/trunk/rpm2cpio.sh", self.mypj("rpm2cpio.sh"))
          except:
            print "Unable to fetch the rpm2cpio script."
            os.chdir(self.basedir)
            return False
          
          # Fetch VOMS source rpm. LFC depends on VOMS.
          try:
            if os.path.isdir(self.mypj("voms")):
              shutil.rmtree(self.mypj("voms"))
            os.mkdir(self.mypj("voms"))
            vomsdownloadlink = "http://download.nordugrid.org/packages/voms/releases/"+self.vomsversion+"-1/fedora/11/x86_64/voms-"+self.vomsversion+"-1.fc11.src.rpm"
            urllib.urlretrieve(vomsdownloadlink, self.mypj("voms", "voms-"+self.vomsversion+"-1.fc11.src.rpm"))

            # rpm2cpio writes output to cwd.
            os.chdir(self.mypj("voms"))
            subprocess.Popen(["sh", self.mypj("rpm2cpio.sh"), self.mypj("voms", "voms-"+self.vomsversion+"-1.fc11.src.rpm")], stdout = subprocess.PIPE, stderr = subprocess.PIPE).wait()
          except IOError:
            print "Unable to fetch VOMS source RPM"
            os.chdir(self.basedir)
            return False

          # Fetch LCG-DM source rpm. (lcgdm)
          try:
            if os.path.isdir(self.mypj("lcgdm")):
              shutil.rmtree(self.mypj("lcgdm"))
            os.mkdir(self.mypj("lcgdm"))
            lfcdownloadlink = "http://download.nordugrid.org/packages/lcgdm/releases/"+self.lcgdmversion+"-3/fedora/12/x86_64/lcgdm-"+self.lcgdmversion+"-3.fc12.src.rpm"
            urllib.urlretrieve(lfcdownloadlink, self.mypj("lcgdm", "lcgdm-"+self.lcgdmversion+"-3.fc12.src.rpm"))

            # rpm2cpio writes output to cwd.
            os.chdir(self.mypj("lcgdm"))
            subprocess.Popen(["sh", self.mypj("rpm2cpio.sh"), self.mypj("lcgdm", "lcgdm-"+self.lcgdmversion+"-3.fc12.src.rpm")], stdout = subprocess.PIPE, stderr = subprocess.PIPE).wait()
            
          except IOError:
            print "Unable to fetch LCG-DM source RPM"
            os.chdir(self.basedir)
            return False

          try:
            urllib.urlretrieve("http://svn.nordugrid.org/trac/packaging/export/599/macports/trunk/lcgdm-darwin.patch", self.mypj("lcgdm", "lcgdm-darwin.patch"))
          except IOError:
            print "Unable to fetch LCG-DM Mac OS X patch"
            os.chdir(self.basedir)
            return False

        if self.channel == "svn":
          self.source_dir = "nordugrid-arc-svn"
          svn_args = ["co", "http://svn.nordugrid.org/repos/nordugrid/arc1/trunk", self.mypj(self.name, self.source_dir)]
          if self.version:
              svn_args += ["-r", str(self.version)]
          print " ".join(["svn"]+svn_args)
          sys.stdout.flush()
          if subprocess.Popen(["svn"] + svn_args, stderr = subprocess.PIPE).wait() != 0:
            print "Unable to checkout svn source."
            return False
          if not self.version:
              self.version = subprocess.Popen(["svnversion", self.mypj(self.name, self.source_dir)], stdout = subprocess.PIPE, stderr = subprocess.PIPE).communicate()[0].strip()
              self.relversion = "svn-r"+self.version
          os.chdir(self.basedir)
          return True

        if self.channel == "nightlies":
            if not self.version:
                self.version = str(datetime.date.today())
                if not self.relversion:
                    self.relversion = self.version
                
            # Get nightly source name.
            try:
                output = "".join(urllib.urlopen("http://download.nordugrid.org/nightlies/nordugrid-arc/trunk/"+str(self.version)+"/src/").readlines())
                self.source = re.search("nordugrid-arc-\d{12}.tar.gz", output).group(0)
                self.source_dir = self.source[:-7]
            except IOError:
                print "Unable to locate nightly source."
                return False

            downloadlink = "http://download.nordugrid.org/nightlies/nordugrid-arc/trunk/"+self.version+"/src/"+self.source
        else:
            self.source_dir = "nordugrid-arc-"+self.version
            self.source = self.source_dir+".tar.gz"
            downloadlink = "http://download.nordugrid.org/packages/nordugrid-arc/"+self.channel+"/"+self.version+"/src/"+self.source
        
            
        try:
            if os.path.isfile(self.mypj(self.name, self.source)):
                os.remove(self.mypj(self.name, self.source))
            urllib.urlretrieve(downloadlink, self.mypj(self.name, self.source))
        except IOError:
            print "Unable to fetch source."
            return False

        os.chdir(self.basedir)
        return True

    def modifyportfile(self, pkgname):
        '''Returns a modified copy of a portfile for the specified package.
        The returned portfile have dependencies removed, and package name changed
        to "<pkgname>-arc" to avoid conflicts. The PKG_CONFIG_LIBDIR
        environment variable is also set to use own and system pkgconfig files.
        '''
        # Modify Portfile to our purpose.
        portfile = self.port(["cat", pkgname])["stdout"]

        # Put escaped lines on one line.
        portfile = re.sub("\s*\\\\\n\s*", " ", portfile)

        # Dont use the ${name} or ${distname} variable
        portfile = re.sub("\$\{?name\}?", pkgname, portfile)
        portfile = portfile.replace("${distname}", pkgname+"-${version}")

        # If not set, set distname since name was modified. MacPorts rely on it.
        if not re.search("^distname", portfile, re.M):
          portfile += os.linesep + "distname "+pkgname+"-${version}"

        # Use own and system pkgconfig files
        if re.search("^configure.env-append", portfile, re.M):
          portfile = re.sub("^(configure.env-append.*)$", "\\1 PKG_CONFIG_LIBDIR="+self.mypj("install/lib/pkgconfig")+":/usr/lib/pkgconfig", portfile, re.M)
        elif re.search("^configure\s+{", portfile, re.M):
          portfile = re.sub('(\nconfigure {[^\n]*\n)', '\\1    set env(PKG_CONFIG_LIBDIR) '+self.mypj("install/lib/pkgconfig")+':/usr/lib/pkgconfig\n', portfile)
        else:
          portfile += os.linesep + "configure.env-append PKG_CONFIG_LIBDIR="+self.mypj("install/lib/pkgconfig")+":/usr/lib/pkgconfig"

        # Specify that port installs files outside common MacPorts structure (avoids massive warnings)
        portfile += os.linesep + "destroot.violate_mtree yes"

        portfile = re.sub("\${prefix}/share/libtool", "/opt/local/share/libtool", portfile)

        # Install Perl modules to prefix.
        portfile = re.sub("\${perl_vendor_lib}", "${prefix}/lib/perl5/vendor_perl", portfile)

        # Split into lines, to be able to parse line by line.
        portfile = portfile.splitlines()
        for i in range(len(portfile)):
            # Dont let MacPorts deal with dependencies. Dont perform archcheck.
            if portfile[i][:8] == "depends_" or portfile[i][:15] == "archcheck.files":
                portfile[i] = ''
            # Rename package as to not conflict with existing packages.
            elif portfile[i][:5]  == "name ":
                portfile[i] = "name "+pkgname+"-arc"

            # Modify master_sites since name was modified.
            elif portfile[i][:13] == "master_sites ":
                portfile[i] = re.sub("(master_sites\s*gnu)", "\\1:"+pkgname, portfile[i])

        return os.linesep.join(portfile)

    def linkcheck(self, path):
        # Check if executables and libraries are linked correctly.
        depslibs = []
        for root, dirs, files in os.walk(path):
            for filename in files:
                absfilename = pj(root, filename)
                if ".dylib" in absfilename or "/bin/" in absfilename:
                    depslibs.append(absfilename)

        if depslibs:
            inconsistentlinks = {}
            linked_libraries = otool(depslibs)
            for exec_lib in linked_libraries:
                for link in linked_libraries[exec_lib]:
                    if link[:8] != "/usr/lib" and link[:len(self.workdir)] != self.workdir and link[:15] != "/System/Library":
                        if not inconsistentlinks.has_key(exec_lib):
                            inconsistentlinks[exec_lib] = []
                        inconsistentlinks[exec_lib].append(link)

            if inconsistentlinks:
                print "The following libraries should not be linked against:"
                for key in inconsistentlinks:
                    print "%s => %s" % (key, ", ".join(inconsistentlinks[key]))
                return False
        return True

    def installport(self, portname, prefix ='install'):
        if os.path.isdir(self.mypj(portname)):
            shutil.rmtree(self.mypj(portname))
        os.mkdir(self.mypj(portname))

        if not os.path.isdir(self.mypj(prefix)):
            os.makedirs(self.mypj(prefix))

        # Create modified portfile
        portfile = open(self.mypj(portname, 'Portfile'), 'w')
        portfile.write(self.modifyportfile(portname))
        portfile.close()

        # Make link to patch files.
        port_dir = self.port(["dir", portname])
        if port_dir["success"] and os.path.isdir(pj(port_dir["stdout"].strip(), "files")):
            os.symlink(pj(port_dir["stdout"].strip(), "files"), self.mypj(portname, "files"))

        time.sleep(1)

        # Build package
        if not self.port(["destroot", "-D", self.mypj(portname), "prefix="+self.mypj(prefix)], True, False)["success"]:
            print "Unable to build and destroot %s package." % portname
            return False

        # Get MacPort working directory
        port_work = self.port(["work", "-D", self.mypj(portname)], True)
        if not port_work["success"] or not port_work["stdout"]:
            print "Unable to obtain workpath for %s package." % portname
            return False

        # Check if correctly linked
        if not self.linkcheck(pj(port_work["stdout"].strip(), 'destroot', self.mypj(prefix))):
            print "The %s package is inconsistently linked." % portname
            return False

        # Install package
        if not self.port(["install", "-D", self.mypj(portname), "prefix="+self.mypj(prefix)], True, False)["success"]:
            print "Unable to install %s package." % portname
            return False

        return True

    def buildvoms(self):
      if os.path.isdir(self.mypj("voms", "voms-"+self.vomsversion)):
        shutil.rmtree(self.mypj("voms", "voms-"+self.vomsversion))

      tarfile.open(self.mypj("voms", "voms-"+self.vomsversion+".tar.gz")).extractall(self.mypj("voms"))
      
      os.chdir(self.mypj("voms", "voms-"+self.vomsversion))
      
      voms_spec = open(self.mypj("voms", "voms.spec")).read()
      patches = re.findall("^Patch\d+:\s+%{name}-(.*)$", voms_spec, re.M)
      for patch in patches:
        if subprocess.Popen(["patch", "-p1", "-i", "../voms-"+patch], stdout = subprocess.PIPE, stderr = subprocess.PIPE).wait() != 0:
          os.chdir(self.basedir)
          print "Unable to patch VOMS"
          return False
      
      # Fix location dir
      # Fix default Globus location
      # Fix default vomses file location
      # Use pdflatex
      if subprocess.Popen(["gsed", "-e", 's!\(LOCATION_DIR.*\)"\${\?prefix\}?"!\\1""!g', "-i", self.mypj("voms", "voms-"+self.vomsversion, "project/acinclude.m4")]).wait() != 0 or \
         subprocess.Popen(["gsed", "-e", "s!\(GLOBUS_LOCATION\)!{\\1:-/opt/local}!",     "-i", self.mypj("voms", "voms-"+self.vomsversion, "project/voms.m4")]).wait() != 0 or \
         subprocess.Popen(["gsed", "-e", "s!/opt/glite/etc/vomses!/etc/vomses!",         "-i", self.mypj("voms", "voms-"+self.vomsversion, "src/api/ccapi/voms_api.cc")]).wait() != 0 or \
         subprocess.Popen(["gsed", "-e", "s!^\(USE_PDFLATEX *= *\)NO!\\1YES!",           "-i", self.mypj("voms", "voms-"+self.vomsversion, "src/api/ccapi/Makefile.am")]).wait() != 0:
         print "Unable to modify VOMS source files with gsed."
         os.chdir(self.basedir)
         return False

      # rebootstrap
      if subprocess.Popen(["./autogen.sh"]).wait() != 0:
        print "Unable to rebootstrap VOMS"
        os.chdir(self.basedir)
        return False
      
      configure_args = ["--prefix="+self.mypj("install"),  "--disable-glite", "--disable-java", "PKG_CONFIG_LIBDIR="+self.mypj("install", "lib/pkgconfig")+":/usr/lib/pkgconfig"]
      if subprocess.Popen(["./configure"] + configure_args).wait() != 0:
        print "Unable to configure VOMS"
        os.chdir(self.basedir)
        return False
      
      if subprocess.Popen(["make", "-j4"]).wait() != 0:
        print "Unable to build VOMS"
        os.chdir(self.basedir)
        return False
      
      if subprocess.Popen(["make", "install"]).wait() != 0:
        print "Unable to install VOMS"
        os.chdir(self.basedir)
        return False
      
      os.rename(self.mypj("install", "include", "glite/security/voms"), self.mypj("install", "include", "voms"))
      
      os.chdir(self.basedir)
      return True

    def buildlcgdm(self):
      if os.path.isdir(self.mypj("lcgdm", "lcgdm-"+self.lcgdmversion)):
        shutil.rmtree(self.mypj("lcgdm", "lcgdm-"+self.lcgdmversion))

      tarfile.open(self.mypj("lcgdm", "lcgdm-"+self.lcgdmversion+".tar.gz")).extractall(self.mypj("lcgdm"))
      
      os.chdir(self.mypj("lcgdm", "lcgdm-"+self.lcgdmversion))

      # Patch the usr patch.
      if subprocess.Popen(["gsed", "-e", "s@/usr/include/globus@"+self.mypj("install", "include", "globus")+"@g", "-e" "s@/usr/$(_lib)/globus/include@"+self.mypj("install", "lib", "globus", "include")+"@g", "-i", self.mypj("lcgdm", "lcgdm-usr.patch")]).wait() != 0:
          os.chdir(self.basedir)
          print "Unable to patch LCG-DM (usr patch)."
          return False

      lcgdm_spec = open(self.mypj("lcgdm", "lcgdm.spec")).read()
      patches = re.findall("^Patch\d+:\s+%{name}-(.*)$", lcgdm_spec, re.M)
      for patch in patches:
        if subprocess.Popen(["patch", "-p1", "-i", "../lcgdm-"+patch], stdout = subprocess.PIPE, stderr = subprocess.PIPE).wait() != 0:
          os.chdir(self.basedir)
          print "Unable to patch LCG-DM"
          return False

      if subprocess.Popen(["patch", "-p1", "-i", self.mypj("lcgdm", "lcgdm-darwin.patch")], stdout = subprocess.PIPE, stderr = subprocess.PIPE).wait() != 0 or \
         subprocess.Popen(["gsed", "s!^\(#define SecLibsGSI\(pthr\)\?\)!\\1 -L$(GLOBUS_LOCATION)/lib!", "-i", self.mypj("lcgdm", "lcgdm-"+self.lcgdmversion, "security/Imakefile")]).wait() != 0:
        os.chdir(self.basedir)
        print "Unable to patch LCG-DM (darwin)"
        return False
      
      if subprocess.Popen(["gsed", "s!@@LIBDIR@@!"+self.mypj("install", "lib")+"!", "-i", self.mypj("lcgdm", "lcgdm-"+self.lcgdmversion, "security", "Csec_api_loader.c")]).wait() != 0:
          os.chdir(self.basedir)
          print "Unable to patch LCG-DM (Csec_api_loader.c)"
          return False
      
      # The code violates the strict aliasing rules all over the place...
      # Need to use -fnostrict-aliasing so that the -O2 optimization in
      # optflags doesn't try to use them.
      if subprocess.Popen(["gsed", "s/^CC +=/& -O2 -fno-strict-aliasing/", "-i", self.mypj("lcgdm", "lcgdm-"+self.lcgdmversion, "config", "linux.cf")]).wait() != 0:
          os.chdir(self.basedir)
          print "Unable to patch LCG-DM (no-strict-aliasing)"
          return False

      gsoapversion = subprocess.Popen(["soapcpp2", "-v"], stderr = subprocess.PIPE).communicate()[1].splitlines()[1].split()[-1]

      configure_args = ["lfc"]
      configure_args.append("--verbose")
      configure_args.append("--with-client-only")
      configure_args.append("--with-gsoap-location=/opt/local")
      configure_args.append("--with-gsoap-version="+gsoapversion)
      configure_args.append("--with-voms-location="+self.mypj("install"))
      configure_args.append("--with-id-map-file="+self.mypj("install", "etc", "lcgdm-mapfile"))
      configure_args.append("--with-ns-config-file="+self.mypj("install", "etc", "NSCONFIG"))
      configure_args.append("--with-sysconf-dir="+self.mypj("install", "etc"))
      configure_args.append("--with-globus-location="+self.mypj("install"))

      if subprocess.Popen(["./configure"] + configure_args).wait() != 0:
        print "Unable to configure LCG-DM"
        os.chdir(self.basedir)
        return False
      
      if subprocess.Popen(["make", "-f", "Makefile.ini", "Makefiles"]).wait() != 0:
        print "Unable to create LCG-DM makefiles"
        os.chdir(self.basedir)
        return False
      
      if subprocess.Popen(["make", "-j4", "prefix="+self.mypj("install")]).wait() != 0:
        print "Unable to build LCG-DM"
        os.chdir(self.basedir)
        return False
      
      if subprocess.Popen(["make", "install", "prefix="+self.mypj("install")]).wait() != 0:
        print "Unable to install LCG-DM"
        os.chdir(self.basedir)
        return False


      # Move plugins out of the default library search path
      if not os.path.isdir(self.mypj("install", "lib", "lcgdm")):
          os.mkdir(self.mypj("install", "lib", "lcgdm"))
      for plugin in glob.glob(self.mypj("install", "lib", "libCsec_plugin_*")):
          os.rename(plugin, plugin.replace(self.mypj("install", "lib"), self.mypj("install", "lib", "lcgdm")))

      
      os.chdir(self.basedir)
      return True

    def buildarcclient(self):
        if self.channel != "svn":
          # Extract source code
          tarfile.open(self.mypj(self.name, self.source)).extractall(self.mypj(self.name))
          makefile_to_patch = "Makefile.in"
        else:
          makefile_to_patch = "Makefile.am"
          

        #~ gsed -i "s/@MSGMERGE@ --update/@MSGMERGE@ --update --backup=off/" self.source_dir/po/Makefile.in.in


        # Use aclocal located at self.workdir
        if subprocess.Popen(["gsed", "-i", "s|/opt/local/share/aclocal|"+self.mypj("install/share/aclocal")+"|g", self.mypj(self.name, self.source_dir, makefile_to_patch)]).wait() != 0:
            print "Unable to patch %s" % makefile_to_patch
            return False

        os.chdir(self.mypj(self.name, self.source_dir))

        if self.channel == "svn" and subprocess.Popen(["./autogen.sh"]).wait() != 0:
          print "autogen.sh failed"
          os.chdir(self.basedir)
          return False

        configure_args = []
        configure_args += ["--disable-all", "--enable-hed", "--enable-arclib-client", "--enable-credentials-client", "--enable-data-client", "--enable-srm-client", "--enable-doc", "--enable-cppunit", "--enable-python"]
        configure_args.append("--prefix="+self.mypj(self.name, "install"))
        if self.buildlfc:
            configure_args += ["--enable-lfc", "--with-lfc="+self.mypj("install")]
        configure_args.append("PKG_CONFIG_LIBDIR="+self.mypj("install", "lib/pkgconfig")+":/usr/lib/pkgconfig")
        configure_args.append("PATH=/System/Library/Frameworks/Python.framework/Versions/2.6/bin:"+os.environ["PATH"])

        print "./configure "+" ".join(configure_args)
        sys.stdout.flush()
        if subprocess.Popen(["./configure"] + configure_args).wait() != 0:
            print "configure failed"
            os.chdir(self.basedir)
            return False

        if subprocess.Popen(["make", "-j2"]).wait() != 0:
            print "make failed"
            os.chdir(self.basedir)
            return False

        if self.domakecheck and subprocess.Popen(["make", "check"]).wait() != 0:
            print "make check failed"
            os.chdir(self.basedir)
            return False

        if subprocess.Popen(["make", "install"]).wait() != 0:
            print "make install failed"
            os.chdir(self.basedir)
            return False

        os.chdir(self.basedir)

        # Dont include the following files in the package
        shutil.rmtree(self.mypj(self.name, "install/share/arc/examples/config"), True)
        shutil.rmtree(self.mypj(self.name, "install/share/arc/examples/echo"), True)
        shutil.rmtree(self.mypj(self.name, "install/share/arc/profiles"), True)
        shutil.rmtree(self.mypj(self.name, "install/share/arc/schema"), True)
        shutil.rmtree(self.mypj(self.name, "install/share/doc"), True)
        shutil.rmtree(self.mypj(self.name, "install/man/man5"), True)
        shutil.rmtree(self.mypj(self.name, "install/man/man8"), True )
        shutil.rmtree(self.mypj(self.name, "install/sbin"), True)
        shutil.rmtree(self.mypj(self.name, "install/libexec"), True)

        return True

    def copylibraries(self, depspatterns, topath, excludes = []):
        # Find all library dependencies
        linked_libraries = otool(depspatterns)
        if not linked_libraries:
            print "otool failed"
            return False

        # Only self made libraries should be copied (packaged)
        dependent_libraries = set([ lib for exec_lib in linked_libraries for lib in linked_libraries[exec_lib] if self.mypj("install") in lib and not lib in excludes ])

        # Copy library dependencies
        for lib in dependent_libraries:
            shutil.copy2(lib, topath)

        return True

    def separatelibraries(self):
        if os.path.isdir(self.mypj("packages")):
            shutil.rmtree(self.mypj("packages"))
        os.mkdir(self.mypj("packages"))
        os.makedirs(self.mypj("packages/deps/lib"))
        os.makedirs(self.mypj("packages/globus/lib/arc"))
        if self.buildlfc:
            os.makedirs(self.mypj("packages/lfc/lib/arc"))
            os.makedirs(self.mypj("packages/lfc/lib/lcgdm"))

        if os.path.isdir(self.mypj(self.name, self.arcglobusdir)):
            shutil.rmtree(self.mypj(self.name, self.arcglobusdir))
        os.makedirs(self.mypj(self.name, self.arcglobusdir, "arc"))

        # Move ARC globus modules and libraries in order to separate globus dependency.
        for filename in glob.glob(self.mypj(self.name, "install/lib/arc/libaccARC0.*")) \
                 + glob.glob(self.mypj(self.name, "install/lib/arc/libdmcrls.*")) \
                 + glob.glob(self.mypj(self.name, "install/lib/arc/libdmcgridftp.*")) \
                 + glob.glob(self.mypj(self.name, "install/lib/arc/libmccgsi.*")) \
                 + glob.glob(self.mypj(self.name, "install/lib/libarcglobusutils*")):
            os.rename(filename, filename.replace(self.mypj(self.name, "install/lib"), self.mypj(self.name, self.arcglobusdir)))
        # Copy ARC globus modules and libraries to packages directory.
        for filename in glob.glob(self.mypj(self.name, self.arcglobusdir, "arc/lib*")) + glob.glob(self.mypj(self.name, self.arcglobusdir, "lib*")):
            shutil.copy2(filename, filename.replace(self.mypj(self.name, self.arcglobusdir), self.mypj("packages/globus/lib")))

        if self.buildlfc:
            if os.path.isdir(self.mypj(self.name, "lfc")):
                shutil.rmtree(self.mypj(self.name, "lfc"))
            os.makedirs(self.mypj(self.name, "lfc/lib/arc"))
            
            # Move ARC LFC modules and libraries in order to separate LFC dependency.
            for filename in glob.glob(self.mypj(self.name, "install/lib/arc/libdmclfc.*")):
                os.rename(filename, filename.replace(self.mypj(self.name, "install"), self.mypj(self.name, "lfc")))
            # Copy ARC LFC modules and libraries to packages directory.
            for filename in glob.glob(self.mypj(self.name, "lfc/lib/arc/lib*")):
                shutil.copy2(filename, filename.replace(self.mypj(self.name), self.mypj("packages")))

        if not self.copylibraries([self.mypj(self.name, "install/bin/*"), self.mypj(self.name, "install/lib/*.dylib"), self.mypj(self.name, "install/lib/arc/*.so")], self.mypj("packages/deps/lib")):
            print "Unable to separate libraries"
            return False
        # Entries to exclude for globus
        globus_excludes = [ lib.replace("packages/deps", "install") for lib in glob.glob(self.mypj("packages/deps/lib/*")) ]
        if not self.copylibraries([self.mypj(self.name, self.arcglobusdir, "arc/*.so"), self.mypj(self.name, self.arcglobusdir, "*.dylib")], self.mypj("packages/globus/lib"), globus_excludes):
            print "Unable to separate Globus libraries"
            return False
        if self.buildlfc:
            # Entries to exclude for LFC
            lfc_excludes = globus_excludes + [ lib.replace("packages/globus", "install") for lib in glob.glob(self.mypj("packages/globus/lib/*")) ]
            if not self.copylibraries([self.mypj(self.name, "lfc/lib/arc/*.so"), self.mypj("install/lib/lcgdm/*.dylib")], self.mypj("packages/lfc/lib"), lfc_excludes):
                print "Unable to separate LFC libraries"
                return False

        # Copy globus loadable module as well.
        for filename in glob.glob(self.mypj("install/lib/libglobus_*.so")):
            shutil.copy2(filename, filename.replace("install/lib", "packages/globus/lib"))

        if self.buildlfc:
            # Copy LFC loadable module as well.
            for filename in glob.glob(self.mypj("install/lib/lcgdm/*")):
                shutil.copy2(filename, filename.replace("install", "packages/lfc"))
            
        return True

    def userelativelinking(self):
        if not (changeinstallnames(self.mypj("packages/globus/lib/arc/*.so"), {self.mypj(self.name, "install/lib") : "@loader_path/..", self.mypj("install/lib") : "@loader_path/.."}) and \
                changeinstallnames(self.mypj("packages/globus/lib/*.dylib"),  {self.mypj(self.name, "install/lib") : "@loader_path",    self.mypj("install/lib") : "@loader_path"}) and \
                changeinstallnames(self.mypj("packages/globus/lib/*.so"),     {self.mypj(self.name, "install/lib") : "@loader_path",    self.mypj("install/lib") : "@loader_path"}) and \
                changeinstallnames(self.mypj("packages/deps/lib/*.dylib"), {self.mypj("install/lib") : "@loader_path"}) and \
                changeinstallnames(self.mypj(self.name, "install/lib/*.dylib"),  {self.mypj(self.name, "install/lib") : "@loader_path"        , self.mypj("install/lib") : "@loader_path"}) and \
                changeinstallnames(self.mypj(self.name, "install/lib/arc/*.so"), {self.mypj(self.name, "install/lib") : "@loader_path/.."     , self.mypj("install/lib") : "@loader_path/.."}) and \
                changeinstallnames(self.mypj(self.name, "install/bin/*"),        {self.mypj(self.name, "install/lib") : "@loader_path/../lib" , self.mypj("install/lib") : "@loader_path/../lib"}) and \
                changeinstallnames(self.mypj(self.name, "install/lib/python2.6/site-packages/_arc.so"), {self.mypj(self.name, "install/lib") : "@loader_path/../.." , self.mypj("install/lib") : "@loader_path/../.."})):
            print "Unable to change library links to use relative linking"
            return False

        if self.buildlfc and \
           not (changeinstallnames(self.mypj("packages/lfc/lib/arc/*.so"), {self.mypj(self.name, "install/lib") : "@loader_path/..", self.mypj("install/lib") : "@loader_path/.."}) and \
                changeinstallnames(self.mypj("packages/lfc/lib/lcgdm/*.dylib"), {self.mypj("install/lib") : "@loader_path/.."}) and \
                changeinstallnames(self.mypj("packages/lfc/lib/*.dylib"), {self.mypj("install/lib") : "@loader_path"})):
            print "Unable to change LFC library links to use relative linking"
            return False
        return True

    def createdmg(self):
        volname = "NorduGrid-ARC-client-"+self.relversion
        appname = "ARC"
        if self.channel == "nightlies":
            appname += " nightly"
        elif self.channel == "svn":
            appname += " svn"
        
        if os.path.isdir(self.mypj(appname+".app")):
            shutil.rmtree(self.mypj(appname+".app"))
        os.makedirs(self.mypj(appname+".app/Contents/MacOS"))
        os.mkdir(self.mypj(appname+".app/Contents/Resources"))

        app_setup_script = open(self.mypj(appname+".app/Contents/MacOS/arc-client-setup.sh"), 'w')
        app_setup_script.writelines("""
# If you want to make the setup carried out here permanent you should put
# the \"export\" statements in a setup file used by your favourite shell.
# E.g.: ${HOME}/.bash_rc, ${HOME}/.profile, etc.
# NOTE: The `dirname \"${BASH_SOURCE[0]}\"` call must be replaced with the
#       absolute path to the location of ARC.
#       E.g.: "/Applications/ARC/Contents/MacOS"
# Also if you do not want to have ARC located in the Applications folder you
# can move all the directories contained in the
# "/Applications/ARC/Contents/MacOS" directory to your desired location, and
# then also remember to set the ARC_LOCATION environment variable
# accordingly.


# Set the ARC_LOCATION environment variable. Needed since ARC is installed in a non default location.
export ARC_LOCATION="$( cd $( dirname "${BASH_SOURCE[0]}" ) && pwd )"
# Include path to ARC client executables in PATH environment variable. Also add path to the Python executable which was linked against.
export PATH="${ARC_LOCATION}/bin:/System/Library/Frameworks/Python.framework/Versions/2.6/bin:${PATH}"
# Set the ARC_PLUGIN_PATH enviroment path to the location of ARC modules.
export ARC_PLUGIN_PATH="${ARC_LOCATION}/lib/arc"
# For the ARC Globus modules to work the GLOBUS_LOCATION environment variable need to be set. 
export GLOBUS_LOCATION="${ARC_LOCATION}"
# For the ARC Python bindings to work the PYTHONPATH need to be set.
export PYTHONPATH="${ARC_LOCATION}/lib/python2.6/site-packages"
# Set the path to the directory containing CA Certificates
export X509_CERT_DIR="${ARC_LOCATION}/etc/grid-security/certificates"
echo "Instructions for using ARC in a regular Terminal can be found here:"
echo "${ARC_LOCATION}/$( basename ${BASH_SOURCE[0]} )"
echo
echo "ARC client environment ready"
""")
        app_setup_script.close()
        
        app_start_script = open(self.mypj(appname+".app/Contents/MacOS/ARC"), 'w')
        app_start_script.writelines("""#!/usr/bin/osascript
# Delay otherwise application doesnt show up in the launch bar
delay 1

set MacARCPath to path to application "%(appname)s"
set ARCPath to POSIX path of MacARCPath

tell application "Terminal"
  activate
  do script "source \\\"" & ARCPATH & "Contents/MacOS/arc-client-setup.sh\\\""

# Get ID of Terminal window just opened. Method assumes the window is the frontmost (maybe not reliable).
  set w_id to 0
  set nWindows to number of windows
  repeat with i from 1 to nWindows
    if frontmost of window 1 then
      set w_id to id of window 1
    end if
  end repeat

# Wait till Terminal window is closed, as to keep the ARC application in the launch bar.
  set window_is_open to true
  repeat while window_is_open
    set nWindows to number of windows
    set window_is_open to false 
    repeat with i from 1 to nWindows
      if id of window i is equal w_id then
        set window_is_open to true
        delay 2
        exit repeat
      end if
    end repeat
  end repeat
end tell""" % {"appname" : appname} )
        app_start_script.close()
        os.chmod(self.mypj(appname+".app/Contents/MacOS/ARC"), stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

        app_info_plist = open(self.mypj(appname+".app/Contents/Info.plist"), 'w')
        app_info_plist.writelines("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>CFBundleName</key><string>%(appname)s</string>
    <key>CFBundleDisplayName</key><string>%(appname)s</string>
    <key>CFBundleGetInfoString</key><string>%(name)s</string>
    <key>CFBundleIdentifier</key><string>org.nordugrid</string>
    <key>CFBundleIconFile</key><string>arc.icns</string>
    <key>CFBundleVersion</key><string>%(version)s</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleSignature</key><string>NOGR</string>
    <key>CFBundleExecutable</key><string>ARC</string>
  </dict>
</plist>""" % {"appname" : appname, "name" : self.name, "version" : self.relversion})
        app_info_plist.close()

        # Copy all needed files to ARC.app/Contents/MacOS directory.
        needed_paths = [self.mypj("packages/deps"), self.mypj("packages/globus")]
        if self.buildlfc:
            needed_paths.append(self.mypj("packages/lfc"))
        needed_paths += [self.mypj(self.name, "install"), self.mypj("igtf-certificates/install")]
        for install_path in needed_paths:
            for root, dirs, files in os.walk(install_path):
                for d in dirs:
                    if not os.path.isdir(pj(root, d).replace(install_path, self.mypj(appname+".app/Contents/MacOS"))):
                        os.mkdir(pj(root, d).replace(install_path, self.mypj(appname+".app/Contents/MacOS")))
                for f in files:
                    shutil.copy2(pj(root, f), pj(root,f).replace(install_path, self.mypj(appname+".app/Contents/MacOS")))

        try:
            urllib.urlretrieve('http://www.nordugrid.org/images/Logo_ARC-ball.png', self.mypj("arc.png"))
            sips_proc = subprocess.Popen(["sips", "--resampleWidth", "128", "-s", "format","icns", self.mypj("arc.png"), "--out", self.mypj(appname+".app/Contents/Resources/arc.icns")], stdout = subprocess.PIPE, stderr = subprocess.PIPE)
            stdout, stderr = sips_proc.communicate()
            if sips_proc.returncode != 0:
                print "WARNING: Unable to convert PNG to ICNS format"
        except IOError:
            print "WARNING: Unable to fetch ARC-logo to use as APP icon"

        app_size = sum(os.path.getsize(os.path.join(root, file)) for root, dir, files in os.walk(self.mypj(appname+".app")) for file in files)
        # Convert to Mb, and increase size a little so the DMG will not be too small.
        app_size = app_size/1024/1024+20

        dmg_name = self.name+"-"+self.relversion+"-snow_leopard-"+self.architecture
        
        if os.path.isfile(self.mypj(dmg_name+".tmp.dmg")):
            os.remove(self.mypj(dmg_name+".tmp.dmg"))

        # Create DMG
        hdiutil_proc = hdiutil(["create", "-srcfolder", self.mypj(appname+".app"), "-size", str(app_size)+"m", "-fs", "HFS+", "-fsargs", "-c c=64,a=16,e=16", "-format", "UDRW", "-volname", volname, self.mypj(dmg_name+".tmp.dmg")])
        if not hdiutil_proc["success"]:
            print "Unable to create DMG"
            print hdiutil_proc["stdout"]
            print hdiutil_proc["stderr"]
            return False
        
        # Attach and get mount point of DMG
        hdiutil_proc = hdiutil(["attach", "-readwrite", "-noverify", "-noautoopen", self.mypj(dmg_name+".tmp.dmg")])
        if not hdiutil_proc["success"]:
            print "Unable to attach DMG"
            return False

        dev, fstype, mountpoint = hdiutil_proc["stdout"].splitlines()[-1].split(None, 2)

        readme = open(pj(mountpoint, "README"), 'w')
        #readme = open(self.mypj("README"), 'w')
        readme.writelines("""To install ARC simply drag the ARC icon into the Applications folder.

In order to use ARC, you will most likely need a Grid certificate and private key.
ARC will look for the certificate and private key in:
  ${HOME}/.globus/usercert.pem (certificate)
and
  ${HOME}/.globus/userkey.pem (private key)
If these are not present here, ARC will most likely not work as expected.
""")
        readme.close()

        shutil.copy2(self.mypj(self.name, self.source_dir, "LICENSE"), pj(mountpoint, "LICENSE"))

        os.symlink("/Applications", pj(mountpoint, "Applications"))

        try:
            os.mkdir(pj(mountpoint, ".background"))
            urllib.urlretrieve('http://www.nordugrid.org/images/ng-logo.png', pj(mountpoint, ".background", "ng-logo.png"))
        except IOError:
            print "WARNING: Unable to fetch NG-logo to use as background"

        try:
            urllib.urlretrieve('http://svn.nordugrid.org/trac/packaging/export/563/macports/trunk/ARC.app.DS_Store', pj(mountpoint, ".DS_Store"))
        except IOError:
            print "WARNING: Unable to prettify DMG"

        # Syncronize to be sure data was written.
        subprocess.Popen(["sync"]).wait()

        hdiutil(["detach", dev])

        if os.path.isfile(dmg_name+".dmg"):
            os.remove(dmg_name+".dmg")

        # Convert to read-only, compress the DMG and put it in CWD.
        hdiutil_proc = hdiutil(["convert", self.mypj(dmg_name+".tmp.dmg"), "-format", "UDZO", "-imagekey", "zlib-level=9", "-o", dmg_name+".dmg"])
        if not hdiutil_proc["success"]:
            print "Unable to compress DMG"
            print hdiutil_proc["stderr"]
            return False
        
        return True
        
    def build(self):
        print(time.asctime())
        sys.stdout.flush()

        if not (self.requiredpackagescheck() and self.initialise()):
            return False

        print "Building ARC client for Mac OS X with the following options:"
        print "Name: %s" % self.name
        print "Version: %s" % self.version
        print "Channel: %s" % self.channel
        print "Working directory: %s" % self.workdir
        sys.stdout.flush()

        if not self.fetchsource():
            return False

        for package in self.deppackages:
            if not self.installport(package):
                return False

        if self.buildlfc and not (self.buildvoms() and self.buildlcgdm()):
            return False

        if not (self.buildarcclient() and self.installport("igtf-certificates", "igtf-certificates/install")):
            return False

        if not (self.separatelibraries() and self.userelativelinking()):
            return False

        if not (self.createdmg()):
            return False

        # Cleanup
        if self.cleanonsuccess:
            shutil.rmtree(self.workdir)

        print "%s was created successfully" % self.name
        print(time.asctime())

    def __init__(self, workdir = '', source = ''):
        self.workdir = workdir
        self.source = source
        self.basedir = os.getcwd()

        available_channels = ['nightlies', 'svn', 'releases', 'testing', 'experimental']
        self.channel = available_channels[0]
        if os.environ.has_key('ARC_BUILD_CHANNEL') and os.environ['ARC_BUILD_CHANNEL'] in available_channels:
            self.channel = os.environ['ARC_BUILD_CHANNEL']
            if self.channel in available_channels[2:] and not os.environ.has_key('ARC_BUILD_VERSION'):
                print "ARC_BUILD_VERSION environment variable must be set for the \"%s\" channel.", self.channel
                sys.exit(1)

        self.version = self.relversion = ''
        if os.environ.has_key('ARC_BUILD_VERSION') and os.environ['ARC_BUILD_VERSION']:
            if self.channel == "svn":
              try:
                self.version = int(os.environ['ARC_BUILD_VERSION'])
                self.relversion = "svn-r"+os.environ['ARC_BUILD_VERSION']
              except exceptions.ValueError:
                pass
            else:
              self.version = self.relversion = os.environ['ARC_BUILD_VERSION']
        if os.environ.has_key('ARC_BUILD_RELEASEVERSION') and os.environ['ARC_BUILD_RELEASEVERSION']:
            self.relversion = os.environ['ARC_BUILD_RELEASEVERSION']

# Building packages for custom architectures is currently not supported.
#        supported_architectures = ['x86_64', 'i386']
#        self.architecture = supported_architectures[0]
#        if os.environ.has_key('ARC_BUILD_ARCHITECTURE') and os.environ['ARC_BUILD_ARCHITECTURE']:
#            if os.environ['ARC_BUILD_ARCHITECTURE'] not in supported_architectures:
#                print "Architecture \"%s\" not supported", os.environ['ARC_BUILD_ARCHITECTURE']
#                sys.exit(1)

        self.domakecheck = (os.environ.has_key('ARC_BUILD_MAKECHECK') and os.environ['ARC_BUILD_MAKECHECK'] == "yes")

        self.buildlfc = (os.environ.has_key('ARC_BUILD_LFC') and os.environ['ARC_BUILD_LFC'] == "yes")
        if self.buildlfc:
          self.vomsversion = "1.9.19.2"
          self.lcgdmversion = "1.8.0.1"

        self.cleanonsuccess = (not os.environ.has_key('ARC_BUILD_CLEANONSUCCESS') or os.environ['ARC_BUILD_CLEANONSUCCESS'] != "no")

        if not os.environ.has_key('ARC_BUILD_INTERACTIVE') or os.environ['ARC_BUILD_INTERACTIVE'] != "yes":
            self.build()

arcpt = ARCPackageTool()
