#!/usr/bin/python
#
# This script creates a Mac OS X NorduGrid ARC standalone package.
# The following environment variables are used to control the outcome:
# ARC_BUILD_CHANNEL (nightlies, releases, testing, experimental)
# ARC_BUILD_VERSION (e.g. 1970-01-01, 1.0.0...)
# ARC_BUILD_ARCHITECTURE (x86_64, i386)
# ARC_BUILD_MAKECHECK (no, yes)
# ARC_BUILD_GLOBUS (yes, no)
# ARC_BUILD_INTERACTIVE (no, yes)
# ARC_BUILD_DEBUG (no, yes)
#
# TODO:
# * Upload package to download.nordugrid.org
# * Add a 'Finish Up' entry in the installer

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



class CreateStandalone:
    ## DEFAULT VALUES.
    # Install package to the specified location.
    install_location = "/opt/local/nordugrid"
    name = "nordugrid-arc-standalone"

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
        self.workdir = tempfile.mkdtemp('', 'arcstandalone-workdir-')

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

        if self.channel == "nightlies":
            if not self.version:
                self.version = str(datetime.date.today())
                if not self.relversion:
                    self.relversion = self.version
                
            # Get nigthly source name.
            try:
                output = "".join(urllib.urlopen("http://download.nordugrid.org/nightlies/nordugrid-arc/trunk/"+str(self.version)+"/src/").readlines())
                self.source = re.search("nordugrid-arc-\d{12}.tar.gz", output).group(0)
            except IOError:
                print "Unable to locate nightly source."
                return False

            downloadlink = "http://download.nordugrid.org/nightlies/nordugrid-arc/trunk/"+self.version+"/src/"+self.source
        else:
            self.source = "nordugrid-arc-"+self.version+".tar.gz"
            downloadlink = "http://download.nordugrid.org/software/nordugrid-arc/"+self.channel+"/"+self.version+"/src/"+self.source

        try:
            if os.path.isfile(self.mypj(self.name, self.source)):
                os.remove(self.mypj(self.name, self.source))
            urllib.urlretrieve(downloadlink, self.mypj(self.name, self.source))
        except IOError:
            print "Unable to fetch source."
            return False

        return True

    def modifyportfile(self, pkgname):
        '''Returns a modified copy of a portfile for the specified package.
        The returned portfile have dependencies removed, and package name changed
        to "<pkgname>-arcstandalone" to avoid conflicts. The PKG_CONFIG_LIBDIR
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
                portfile[i] = "name "+pkgname+"-arcstandalone"

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
        if not self.port(["destroot", "-D", self.mypj(portname), "prefix="+self.mypj(prefix), "build_arch="+self.architecture], True, False)["success"]:
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
        if not self.port(["install", "-D", self.mypj(portname), "prefix="+self.mypj(prefix), "build_arch="+self.architecture], True, False)["success"]:
            print "Unable to install %s package." % portname
            return False

        return True

    def buildarcclient(self):
        # Extract source code
        tarfile.open(self.mypj(self.name, self.source)).extractall(self.mypj(self.name))

        source_dir = self.mypj(self.name, self.source[:-7])

        #~ gsed -i "s/@MSGMERGE@ --update/@MSGMERGE@ --update --backup=off/" source_dir/po/Makefile.in.in

        # Use aclocal located at self.workdir
        if subprocess.Popen(["gsed", "-i", "s|/opt/local/share/aclocal|"+self.mypj("install/share/aclocal")+"|g", pj(source_dir, "Makefile.in")]).wait() != 0:
            print "Unable to patch Makefile.in"
            return False

        basedir = os.getcwd()

        os.chdir(source_dir)

        configure_args = []
        configure_args += ["--disable-all", "--enable-hed", "--enable-arclib-client", "--enable-credentials-client", "--enable-data-client", "--enable-srm-client", "--enable-doc", "--enable-cppunit", "--enable-python"]
        configure_args.append("--prefix="+self.mypj(self.name, "install"))
        configure_args.append("PKG_CONFIG_LIBDIR="+self.mypj("install", "lib/pkgconfig")+":/usr/lib/pkgconfig")
        configure_args.append("PATH=/System/Library/Frameworks/Python.framework/Versions/Current/bin:"+os.environ["PATH"])

        if subprocess.Popen(["./configure"] + configure_args).wait() != 0:
            print "configure failed"
            return False

        if subprocess.Popen(["make", "-j2"]).wait() != 0:
            print "make failed"
            os.chdir(basedir)
            return False

        if self.domakecheck and subprocess.Popen(["make", "check"]).wait() != 0:
            print "make check failed"
            os.chdir(basedir)
            return False

        if subprocess.Popen(["make", "install"]).wait() != 0:
            print "make install failed"
            os.chdir(basedir)
            return False

        os.chdir(basedir)

        # Dont include the following files in the package
        shutil.rmtree(self.mypj(self.name, "install/share/arc/examples/config"))
        shutil.rmtree(self.mypj(self.name, "install/share/arc/examples/echo"))
        shutil.rmtree(self.mypj(self.name, "install/share/arc/profiles"))
        shutil.rmtree(self.mypj(self.name, "install/share/arc/schema"))
        shutil.rmtree(self.mypj(self.name, "install/share/doc"))
        shutil.rmtree(self.mypj(self.name, "install/man/man5"))
        shutil.rmtree(self.mypj(self.name, "install/man/man8"))
        shutil.rmtree(self.mypj(self.name, "install/sbin"))
        shutil.rmtree(self.mypj(self.name, "install/libexec"))

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

    def createarchive(self, packagedir):
        # Create bill of materials (bom)
        if subprocess.Popen(["mkbom", self.mypj(packagedir), self.mypj(packagedir+".bom")]).wait() != 0:
            print "Unable to create bom for dependency package"
            return False

        # Create pax archive
        pax_args  = []
        pax_args += ["-w", self.mypj(packagedir)] # Input path
        pax_args += ["-f", self.mypj(packagedir+".pax")] # Output file
        pax_args += ["-x", "cpio"] # Archive
        pax_args += ["-s", "/"+self.mypj(packagedir).replace("/", "\/")+"/"+self.install_location.replace("/", "\/")+"/"] # Replacement pattern
        if subprocess.Popen(["pax"] + pax_args).wait() != 0:
            print "Unable to create pax archive"
            return False

        # Compress pax archive
        paxf = open(self.mypj(packagedir+'.pax'), 'rb')
        paxf_gz = gzip.open(self.mypj(packagedir+'.pax.gz'), 'wb')
        paxf_gz.writelines(paxf)
        paxf_gz.close()
        paxf.close()

        return True

    def separatelibraries(self):
        if os.path.isdir(self.mypj("packages")):
            shutil.rmtree(self.mypj("packages"))
        os.mkdir(self.mypj("packages"))
        os.makedirs(self.mypj("packages/deps/lib"))
        os.makedirs(self.mypj("packages/globus/lib/arc"))
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

        # Entries to exclude for globus
        globus_excludes = [ lib.replace("packages/deps", "install") for lib in glob.glob(self.mypj("packages/deps/lib/*")) ]

        if not (self.copylibraries([self.mypj(self.name, "install/bin/*"), self.mypj(self.name, "install/lib/*.dylib"), self.mypj(self.name, "install/lib/arc/*.so")], self.mypj("packages/deps/lib")) and \
                self.copylibraries([self.mypj(self.name, self.arcglobusdir, "arc/*.so"), self.mypj(self.name, self.arcglobusdir, "*.dylib")], self.mypj("packages/globus/lib"), globus_excludes)):
            print "Unable to separate libraries"
            return False
            
        return True

    def userelativelinking(self):
        if not (changeinstallnames(self.mypj("packages/globus/lib/arc/*.so"), {self.mypj(self.name, "install/lib") : "@loader_path/..", self.mypj("install/lib") : "@loader_path/.."}) and \
                changeinstallnames(self.mypj("packages/globus/lib/*.dylib"),  {self.mypj(self.name, "install/lib") : "@loader_path",    self.mypj("install/lib") : "@loader_path"}) and \
                changeinstallnames(self.mypj("packages/deps/lib/*.dylib"), {self.mypj("install/lib") : "@loader_path"}) and \
                changeinstallnames(self.mypj(self.name, "install/lib/*.dylib"),  {self.mypj(self.name, "install/lib") : "@loader_path"        , self.mypj("install/lib") : "@loader_path"}) and \
                changeinstallnames(self.mypj(self.name, "install/lib/arc/*.so"), {self.mypj(self.name, "install/lib") : "@loader_path/.."     , self.mypj("install/lib") : "@loader_path/.."}) and \
                changeinstallnames(self.mypj(self.name, "install/bin/*"),        {self.mypj(self.name, "install/lib") : "@loader_path/../lib" , self.mypj("install/lib") : "@loader_path/../lib"}) and \
                changeinstallnames(self.mypj(self.name, "install/lib/python2.6/site-packages/_arc.so"), {self.mypj(self.name, "install/lib") : "@loader_path/../.." , self.mypj("install/lib") : "@loader_path/../.."})):
            print "Unable to change library links to use relative linking"
            return False
        return True

    def completepackage(self):
        if not (self.createarchive("packages/deps") and self.createarchive("packages/globus") and \
                self.createarchive("igtf-certificates/install") and self.createarchive(self.mypj(self.name, "install"))):
            print "Unable to create sub-packages"
            return False

        # Add PATHs to environment by using postinstall script. Copy ReadMe to location.
        postinstall = os.open(self.name+"-"+self.version+".mpkg/Contents/Resources/postinstall")
        postinstall.writelines("""#!/bin/bash
cat << EOF > /etc/paths.d/%(name)s
%(location)s/bin
EOF

cp ${PACKAGE_PATH}/Contents/Resources/ReadMe %(location)s/.
""" % {"location" : self.install_location, "name" : self.name})
        postinstall.close()
        os.chmod(self.mypj(self.name+'-'+self.version+'.mpkg/Contents/Resources/postinstall', 0555))

        shutil.copy2(self.mypj(self.name, self.source[:-7], 'LICENSE'), self.mypj(self.name+'-'+self.version+'.mpkg/Contents/Resources/License'))

        readme = os.open(self.name+"-"+self.version+".mpkg/Contents/Resources/ReadMe")
        readme.writelines("""NOTE: You need to do the following steps after installation of ARC
-------------------------------------------------------------------
Install Grid certificate and private key:

  Copy your user certificate (e.g. usercert.pem) to: $HOME/.globus/usercert.pem
  Copy your user key (e.g. userkey.pem) to: $HOME/.globus/userkey.pem

Also you must set the environment variable GLOBUS_LOCATION to %(location)s in
the shell where ARC will be executed in order for the certain ARC modules to
function. E.g. for bash:
export GLOBUS_LOCATION=%(location)s

Other information
-----------------
Default client.conf, jobs.xml directory location (these directories are
hidden by default):

  $HOME/.arc

Uninstalling this package
-------------------------
To uninstall this package simply remove the '%(location)s' directory and the
file '/etc/paths.d/%(name)s'. Additionally user configuration files might
exist in the $HOME/.arc directory, which can safely be removed.
""" % { "location" : self.install_location, "name" : self.name } )
        readme.close()

        try:
            urllib.urlretrieve('http://www.nordugrid.org/images/ng-logo.png', self.mypj(self.name+'-'+self.version+'.mpkg/Contents/Resources/background'))
            # Put logo in bottom-left corner, and do not scale it.
            #~ '''<key>IFPkgFlagComponentDirectory</key>/i
            #~ <key>IFPkgFlagBackgroundAlignment</key>
            #~ <string>bottomleft</string>
            #~ <key>IFPkgFlagBackgroundScaling</key>
            #~ <string>none</string>'''
            #~ "<string>${name}-${version}.pkg</string><string>required</string>"
                #~ self.name+'-'+self.version+'.mpkg/Contents/Info.plist'
        except IOError:
            print "WARNING: Unable to fetch NG-logo"
        return True

    def createdmg(self):
        volname = "NorduGrid ARC client "+self.relversion
        appname = "ARC"
        if self.channel == "nightlies":
            appname += " nightly"
        
        if os.path.isdir(self.mypj(appname+".app")):
            shutil.rmtree(self.mypj(appname+".app"))
        os.makedirs(self.mypj(appname+".app/Contents/MacOS"))
        os.mkdir(self.mypj(appname+".app/Contents/Resources"))

        
        app_start_script = open(self.mypj(appname+".app/Contents/MacOS/arc-client-setup"), 'w')
        app_start_script.writelines("""#!/usr/bin/osascript
# Delay otherwise application doesnt show up in the launch bar
delay 1

set MacARCPath to path to application "%(appname)s"
set ARCPath to POSIX path of MacARCPath

tell application "Terminal"
  activate
  set currenttab to do script "export PATH=\\\"" & ARCPath & "Contents/MacOS/bin:/System/Library/Frameworks/Python.framework/Versions/Current/bin:${PATH}\\\""
  do script "export ARC_LOCATION=\\\"" & ARCPath & "Contents/MacOS\\\"" in currenttab
  do script "export ARC_PLUGIN_PATH=\\\"" & ARCPath & "Contents/MacOS/lib/arc\\\"" in currenttab
  do script "export PYTHONPATH=\\\"" & ARCPath & "Contents/MacOS/lib/python2.6/site-packages\\\"" in currenttab
  do script "export X509_CERT_DIR=\\\"" & ARCPath & "Contents/MacOS/etc/grid-security/certificates\\\"" in currenttab

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
        os.chmod(self.mypj(appname+".app/Contents/MacOS/arc-client-setup"), stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

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
    <key>CFBundleExecutable</key><string>arc-client-setup</string>
  </dict>
</plist>""" % {"appname" : appname, "name" : self.name, "version" : self.relversion})
        app_info_plist.close()

        # Copy all needed files to ARC.app/Contents/MacOS directory.
        for install_path in [self.mypj("packages/deps"), self.mypj("packages/globus"), self.mypj(self.name, "install"), self.mypj("igtf-certificates/install")]:
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
""" % { "location" : self.install_location, "name" : self.name } )
        readme.close()

        shutil.copy2(self.mypj(self.name, self.source[:-7], "LICENSE"), pj(mountpoint, "LICENSE"))

        try:
            os.mkdir(pj(mountpoint, ".background"))
            urllib.urlretrieve('http://www.nordugrid.org/images/ng-logo.png', pj(mountpoint, ".background", "ng-logo.png"))
        except IOError:
            print "WARNING: Unable to fetch NG-logo to use as background"

        prettify_dmg = '''
tell application "Finder"
  tell disk "%(volname)s"
    open
    set current view of container window to icon view
    set toolbar visible of container window to false
    set statusbar visible of container window to false
    set the bounds of container window to {400, 100, 1032, 512}
    set theViewOptions to the icon view options of container window
    set background picture of theViewOptions to file ".background:ng-logo.png"
    set arrangement of theViewOptions to not arranged
    set icon size of theViewOptions to 72
    make new alias file at container window to POSIX file "/Applications" with properties {name:"Applications"}
    set position of item "%(appname)s" of container window to {190, 65}
    set position of item "README" of container window to {525, 65}
    set position of item "Applications" of container window to {400, 300}
    set position of item "License" of container window to {75, 300}
    close
    open
    --update without registering applications
    delay 5
    eject
  end tell
end tell
''' % {"appname" : appname, "volname" : volname}

        osascript_proc   = subprocess.Popen(["osascript"], stdin = subprocess.PIPE, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        osascript_output = osascript_proc.communicate(input = prettify_dmg)
        if osascript_proc.returncode != 0:
            print "Unable to prettify DMG through AppleScript"
            print osascript_output[0]
            print osascript_output[1]
            return False

        subprocess.Popen(["sync"]).wait()
        subprocess.Popen(["sync"]).wait()
        #hdiutil_proc = hdiutil(["detach", dev])

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
        if not (self.requiredpackagescheck() and self.initialise()):
            return False

        print "Building ARC standalone for Mac OS X with the following options:"
        print "Name: %s" % self.name
        print "Version: %s" % self.version
        print "Channel: %s" % self.channel
        print "Install location: %s" % self.install_location
        print "Architecture: %s" % self.architecture
        print "Working directory: %s" % self.workdir

        if not self.fetchsource():
            return False

        for package in self.deppackages:
            if not self.installport(package):
                return False

        if not (self.buildarcclient() and self.installport("igtf-certificates", "igtf-certificates/install")):
            return False

        if not (self.separatelibraries() and self.userelativelinking()):
            return False

        if not (self.createdmg()):
            return False

        # Cleanup
        shutil.rmtree(self.workdir)

        print "%s was created successfully" % self.name
        print(time.asctime())

    def __init__(self, workdir = '', source = ''):
        self.workdir = workdir
        self.source = source

        available_channels = ['nightlies', 'releases', 'testing', 'experimental']
        self.channel = available_channels[0]
        if os.environ.has_key('ARC_BUILD_CHANNEL') and os.environ['ARC_BUILD_CHANNEL'] in available_channels[1:]:
            self.channel = os.environ['ARC_BUILD_CHANNEL']
            if not os.environ['ARC_BUILD_VERSION']:
                print "ARC_BUILD_VERSION environment variable must be set for the \"%s\" channel.", self.channel
                sys.exit(1)

        self.version = self.relversion = ''
        if os.environ.has_key('ARC_BUILD_VERSION') and os.environ['ARC_BUILD_VERSION']:
            self.version = self.relversion = os.environ['ARC_BUILD_VERSION']
        if os.environ.has_key('ARC_BUILD_RELEASEVERSION') and os.environ['ARC_BUILD_RELEASEVERSION']:
            self.relversion = os.environ['ARC_BUILD_RELEASEVERSION']

        supported_architectures = ['x86_64', 'i386']
        self.architecture = supported_architectures[0]
        if os.environ.has_key('ARC_BUILD_ARCHITECTURE') and os.environ['ARC_BUILD_ARCHITECTURE']:
            if os.environ['ARC_BUILD_ARCHITECTURE'] not in supported_architectures:
                print "Architecture \"%s\" not supported", os.environ['ARC_BUILD_ARCHITECTURE']
                sys.exit(1)

            self.architecture = os.environ['ARC_BUILD_ARCHITECTURE']

        self.domakecheck = (os.environ.has_key('ARC_BUILD_MAKECHECK') and os.environ['ARC_BUILD_MAKECHECK'] == "yes")

        if not os.environ.has_key('ARC_BUILD_INTERACTIVE') or os.environ['ARC_BUILD_INTERACTIVE'] != "yes":
            self.build()

cs = CreateStandalone()
