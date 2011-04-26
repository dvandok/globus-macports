#!/bin/bash
#
# This script creates a Mac OS X NorduGrid ARC standalone package.
# Usage: create-standalone.sh [type] [version] [build globus]
#
# TODO:
# * Upload package to download.nordugrid.org
# * Add a 'Finish Up' entry in the installer

test "x${BUILD_ARC_DEBUG}" == "xyes" && set -x


## DEFAULT VALUES.
# Install package to the specified location. Note that the specified location should be a path used exclusively for the standalone.
location=/opt/local/nordugrid
name=nordugrid-arc-standalone
architecture="x86_64"

domakecheck="no"

makeglobus="yes"
arcglobusmoduledir=globus-plugins

# The metapackage should contain the following packages (order matters!):
deppackages=(zlib libiconv libxml2 gettext libsigcxx2 glib2 glibmm libtool)

# The following globus packages are needed for a working ARC0 middleware module. Order matters.
globuspkgs=(libtool common callout openssl gsi-openssl-error gsi-proxy-ssl openssl-module \
            gsi-cert-utils gsi-sysconfig gsi-callback gsi-credential gsi-proxy-core \
            gssapi-gsi gss-assist gssapi-error xio xio-gsi-driver io xio-popen-driver \
            ftp-control ftp-client rls-client)
###


function initialise() {
basedir=`pwd`
workdir=`mktemp -d /tmp/arcstandalone-workdir-XXXXXX`
cd ${workdir}

mkdir -p macports/{registry,logs,software}
ln -s /opt/local/var/macports/sources macports/sources
cp -p /opt/local/var/macports/registry/registry.db macports/registry/.
touch macports/variants.conf
return 0
}

function toggleownmacportconf() {
if test "${1}" = "on"; then
  if test -L ${HOME}/.macports/macports.conf && test "`readlink ${HOME}/.macports/macports.conf`" = "${workdir}/macports.conf"; then
    return
  fi
  
  if test -f ${HOME}/.macports/macports.conf; then
    mv ${HOME}/.macports/macports.conf ${workdir}/macports.conf.orig
  fi
  
  cat << EOF > ${workdir}/macports.conf
# Set the directory in which to install ports. Must match where MacPorts itself is installed.
prefix			/opt/local

# Where to store MacPorts working data
portdbpath		${workdir}/macports

applications_dir	/Applications/MacPorts
frameworks_dir		/opt/local/Library/Frameworks
sources_conf		/opt/local/etc/macports/sources.conf
variants_conf		${workdir}/macports/variants.conf
universal_archs			x86_64 i386
EOF

  ln -s ${workdir}/macports.conf ${HOME}/.macports/macports.conf
elif test "${1}" = "off"; then
  if test -L ${HOME}/.macports/macports.conf && test "`readlink ${HOME}/.macports/macports.conf`" = "${workdir}/macports.conf"; then
    rm ${HOME}/.macports/macports.conf
    if test -f ${workdir}/macports.conf.orig; then
      mv ${workdir}/macports.conf.orig ${HOME}/.macports/macports.conf
    fi
  fi
fi

}

function requiredpackagescheck() {
toggleownmacportconf on
# The following packages are required to be installed to build the stand-alone package.
requiredpkgs=(gsed gperf pkgconfig autoconf automake wget doxygen p5-archive-tar perl5)
pkgsneeded=
installedports=`port installed`
toggleownmacportconf off
for package in ${requiredpkgs[@]}
do
  [[ `echo $installedports | grep -c $package` -eq 0 ]] && pkgsneeded="$pkgsneeded $package"
done

if test "x${pkgsneeded}x" != "xx"
then
  echo "The following packages are required to build the stand-alone:"
  echo $pkgsneeded
  echo "Please install them."
  return 1
fi

return 0
}

function fetchsource() {
# Source need to be downloaded to be able to calculate checksums. Remove old source first.
rm -rf ${workdir}/${name}/files
mkdir -p ${workdir}/${name}/files

if test ${type} == "nightlies"
then
  if test "x${version}" == "x"; then
    version=`date +%F`
  fi
  source=`wget -O - -q http://download.nordugrid.org/nightlies/nordugrid-arc/trunk/${version}/src | grep -o "nordugrid-arc-[0-9]\+.tar.gz" | head -1`

  if test "x${source}" == "x"; then
    echo "Unable to locate source."
    return 1
  fi

  wget -q http://download.nordugrid.org/nightlies/nordugrid-arc/trunk/${version}/src/${source} -O ${workdir}/${name}/files/${source}
else
  source=nordugrid-arc-${version}.tar.gz
  wget -q http://download.nordugrid.org/software/nordugrid-arc/${type}/${version}/src/${source} -O ${workdir}/${name}/files/${source}
fi

if [[ $? != 0 ]]
then
  echo "Unable to fetch source."
  return 1
fi

return 0
}

function createportfile() {
if test ! -f ${workdir}/${name}/files/${source}; then
  echo "Unable to create Portfile. Source ${workdir}/${name}/files/${source} does not exist."
  return 1
fi

# Calculate and insert checksums and insert version.
md5=`md5 ${workdir}/${name}/files/${source} | awk '{ print $NF }'`
sha1=`openssl sha1 ${workdir}/${name}/files/${source} | awk '{ print $NF }'`
rmd160=`openssl rmd160 ${workdir}/${name}/files/${source} | awk '{ print $NF }'`

cat << EOF > ${workdir}/${name}/Portfile
set sourcename nordugrid-arc

PortSystem              1.0

name                \${sourcename}-standalone
version             ${version}
categories          grid
maintainers         NorduGrid
description         \${version} release of the Advanced Resource Connector (ARC)
long_description    \\
        The Advanced Resource Connector (ARC) middleware, introduced by \\
        NorduGrid (www.nordugrid.org), is an open source software solution \\
        enabling production quality computational and data Grids since May \\
        2002.

homepage            http://www.nordugrid.org
platforms           darwin
distfiles           ${source}
checksums           md5     ${md5} \\
                    sha1    ${sha1} \\
                    rmd160  ${rmd160}

worksrcdir          ${source//.tar.gz}
pre-configure       {
    reinplace "s/@MSGMERGE@ --update/@MSGMERGE@ --update --backup=off/" \${worksrcpath}/po/Makefile.in.in
}
configure.env PKG_CONFIG_LIBDIR=\${prefix}/lib/pkgconfig:/usr/lib/pkgconfig
configure.args-append --disable-xmlsec1 --disable-all --enable-hed --enable-arclib-client --enable-credentials-client --enable-data-client --enable-srm-client --enable-doc --enable-cppunit

test.run            yes
test.target         check

post-destroot {
  system "rm -rf \${destroot}/\${prefix}/share/arc/examples/config"
  system "rm -rf \${destroot}/\${prefix}/share/arc/examples/echo"
  system "rm -rf \${destroot}/\${prefix}/share/arc/profiles"
  system "rm -rf \${destroot}/\${prefix}/share/arc/schema"
  system "rm -rf \${destroot}/\${prefix}/share/doc"
  system "rm -rf \${destroot}/\${prefix}/share/man/man8"
  system "rm -rf \${destroot}/\${prefix}/sbin"
  system "rm -rf \${destroot}/\${prefix}/libexec"
  system "rm -rf \${destroot}/Library"
}

destroot.violate_mtree      yes
EOF

return 0
}

function insertpackage() {
pkgname=${1}
pkgversion=${2}

pkgdir=${name}-${version}.mpkg/Contents/
[[ "x${4}x" != "xx" ]] && pkgdir=${pkgdir}/Packages/${4}/Contents/

rm -rf ${pkgdir}/Packages/${pkgname}-arcstandalone-${pkgversion}.pkg
mv -f ${pkgname}/${pkgname}-arcstandalone-${pkgversion}.pkg ${pkgdir}/Packages/.

if [[ $? != 0 ]]; then
  echo "Unable to locate package ${pkgname}/${pkgname}-arcstandalone-${pkgversion}.pkg"
  return 1
fi

gsed -i "/<\/array>/i \\
\     <dict>\\
\       <key>IFPkgFlagPackageLocation</key>\\
\       <string>${pkgname}-arcstandalone-${pkgversion}.pkg</string>\\
\       <key>IFPkgFlagPackageSelection</key>\\
\       <string>${3}</string>\\
\     </dict>
" ${pkgdir}/Info.plist

return 0
}

function makedeppackage() {
pkgname=${1}
rm -rf ${pkgname}
mkdir ${pkgname}
# Modify Portfile  to our purpose.
port cat ${pkgname} | sed -e :a -e '$!N;s/[[:space:]]*\\\n[[:space:]]*/ /;ta' \
                    | sed -e "s/\${name}/${pkgname}/g" \
                    | sed -e "s/\(name[[:space:]]*${pkgname}\)/\1-arcstandalone/" \
                    | sed -e "/^depends_lib/d" \
                    | sed -e "/^archcheck.files/d" \
                    | sed -e "s/^\(master_sites[[:space:]]*gnu\)/\1:${pkgname}/" > ${pkgname}/Portfile

gsed -i "/checksums/i \\
destroot.violate_mtree      yes\\
" ${pkgname}/Portfile

if [[ "x${pkgname}" = "xglibmm" ]]
then
  gsed -i -e "
                  /^checksums/a \\
                  \\
                  configure.env PKG_CONFIG_LIBDIR=${location}/lib/pkgconfig
                  " ${pkgname}/Portfile
fi

# Set distname so source can be fetched.
gsed -i "
             /^[[:space:]]*version[[:space:]]/a \\
             distname ${pkgname}-\${version}\\
             " ${pkgname}/Portfile
# Make link to patch files.
[[ -d `port dir ${pkgname}`/files ]] && ln -s `port dir ${pkgname}`/files ${pkgname}/files
# Wait 1 second before creating package to avoid MacPorts complaining about files in future.
sleep 1
# Make a package.
toggleownmacportconf on
port pkg -D ${pkgname} prefix=${location} build_arch=${architecture} workpath=${workdir}/${pkgname}/work
if [[ $? -ne 0 ]]
then
  echo "Unable to make package ${pkgname}"
  toggleownmacportconf off
  return 1
fi
toggleownmacportconf off

# Move package, so it is not deleted.
pkgversion=`port info --version -D ${pkgname} | awk '{ print $2 }'`
mv -f ${pkgname}/work/${pkgname}-arcstandalone-${pkgversion}.pkg ${pkgname}/.
mv -f ${pkgname}/${pkgname}-arcstandalone-${pkgversion}.pkg/Contents/Resources/English.lproj/Description.plist \
      ${pkgname}/${pkgname}-arcstandalone-${pkgversion}.pkg/Contents/Resources/.
rm -rf ${pkgname}/${pkgname}-arcstandalone-${pkgversion}.pkg/Contents/Resources/English.lproj

description=`port info --long_description -D ${pkgname} | sed "s/^long_description: //"`
description=${description//\//\\\/}

gsed -i "s/<string><\/string>/<string>${description}<\/string>/" \
  ${pkgname}/${pkgname}-arcstandalone-${pkgversion}.pkg/Contents/Resources/Description.plist

toggleownmacportconf on
# Install package since other packages might depend on it.
port install -D ${pkgname} prefix=${location} build_arch=${architecture} workpath=${workdir}/${pkgname}/work

# Sanity check. Check if libraries are linked properly.
depslibs=`port contents -D ${pkgname} | grep ${location} | grep dylib`
toggleownmacportconf off
if [[ -n ${depslibs} ]] && [[ `otool -L ${depslibs} | grep -v ${location} |\
                              grep -v /usr/lib |\
                              grep -c -v /System/Library` -ne 0 ]]
then
  echo "The ${pkgname} package libraries are linked inconsistently."
  otool -L ${depslibs} | grep -v ${location} | grep -v /usr/lib | grep -v /System/Library
  return 1
fi

return 0
}

function makedependencypackages() {
for package in ${deppackages[@]}
do
  makedeppackage $package || return 1
done

return 0
}

function makeglobuspackage() {
pkgname=${1}

export PERL5LIB="${location}/lib/perl5/vendor_perl"

if [[ "${pkgname}" != "grid-packaging-tools" ]]; then
  pkgname=globus-${pkgname}
fi

rm -rf ${pkgname}
mkdir ${pkgname}
# Modify Portfile  to our purpose.
port cat ${pkgname} \
  | sed -e :a -e '$!N;s/[[:space:]]*\\\n[[:space:]]*/ /;ta' \
  | sed -e "s/\${name}/${pkgname}/g" \
  | sed -e "s/\$name/${pkgname}/g" \
  | sed -e "s/\(name[[:space:]]*${pkgname}\)/\1-arcstandalone/" \
  | sed -e "/^depends/d" \
  | sed -e "s@\${prefix}/share/libtool@/opt/local/share/libtool@g" \
  | sed -e "s@\${perl_vendor_lib}@${PERL5LIB}@" \
  | sed -e "/^archcheck.files/d" > ${pkgname}/Portfile

gsed -i "/checksums/i \\
destroot.violate_mtree      yes\\
" ${pkgname}/Portfile

if test "x${pkgname}" == "xglobus-openssl"; then
  gsed -i "/configure {/a \\
    set env(PKG_CONFIG_LIBDIR) ${location}:/usr/lib/pkgconfig\\
" ${pkgname}/Portfile
fi

# Make link to patch files.
[[ -d `port dir ${pkgname}`/files ]] && ln -s `port dir ${pkgname}`/files ${pkgname}/files

# Wait 1 second before creating package to avoid MacPorts complaining about files in future.
sleep 1

if [[ "${pkgname}" == "grid-packaging-tools" ]] || [[ "${pkgname}" == "globus-core" ]];
then
  toggleownmacportconf on
  port install -D ${pkgname} prefix=${location} build_arch=${architecture} workpath=${workdir}/${pkgname}/work
  if [[ $? -ne 0 ]]
  then
    toggleownmacportconf off

    echo "Unable to make package ${pkgname}"
    return 1
  fi

  toggleownmacportconf off
  return 0
fi

toggleownmacportconf on
# Make a package.
port pkg -D ${pkgname} prefix=${location} build_arch=${architecture} workpath=${workdir}/${pkgname}/work
if [[ $? -ne 0 ]]
then
  toggleownmacportconf off
  echo "Unable to make package ${pkgname}"
  return 1
fi
toggleownmacportconf off

# Move package, so it is not deleted.
pkgversion=`port info --version -D ${pkgname} | awk '{ print $2 }'`
mv -f ${pkgname}/work/${pkgname}-arcstandalone-${pkgversion}.pkg ${pkgname}/.
mv -f ${pkgname}/${pkgname}-arcstandalone-${pkgversion}.pkg/Contents/Resources/English.lproj/Description.plist \
      ${pkgname}/${pkgname}-arcstandalone-${pkgversion}.pkg/Contents/Resources/.
rm -rf ${pkgname}/${pkgname}-arcstandalone-${pkgversion}.pkg/Contents/Resources/English.lproj

description=`port info --long_description -D ${pkgname} | sed "s/^long_description: //"`
description=${description//\//\\\/}

gsed -i "s/<string><\/string>/<string>${description}<\/string>/" \
  ${pkgname}/${pkgname}-arcstandalone-${pkgversion}.pkg/Contents/Resources/Description.plist

toggleownmacportconf on
# Install package since others packages might depend on it.
port install -D ${pkgname} prefix=${location} build_arch=${architecture} workpath=${workdir}/${pkgname}/work

# Sanity check. Check if libraries are linked properly.
depslibs=`port contents -D ${pkgname} | grep ${location} | grep dylib`
toggleownmacportconf off
if [[ -n ${depslibs} ]] && [[ `otool -L ${depslibs} | grep -v ${location} |\
                              grep -v /usr/lib |\
                              grep -c -v /System/Library` -ne 0 ]]
then
  echo "The ${pkgname} package libraries are linked inconsistently."
  otool -L ${depslibs} | grep -v ${location} | grep -v /usr/lib | grep -v /System/Library
  return 1
fi

return 0
}

function makeglobuspackages() {
# Make globus packages. grid-packaging-tools and globus-core is needed to build the other packages.
makeglobuspackage grid-packaging-tools || return 1
makeglobuspackage core || return 1

for package in ${globuspkgs[@]}
do
  makeglobuspackage $package || return 1
done

return 0
}

function makearcmetapackage() {
# Create the Nordugrid ARC stand-alone package.
toggleownmacportconf on

# Build and test the stand-alone
port -d build -D ${workdir}/${name} prefix=${location} build_arch=${architecture} workpath=${workdir}/${name}/work distpath=${workdir}/${name}/files
if [[ $? != 0 ]]
then
  toggleownmacportconf off
  echo "Building ${name} failed"
  return 1
fi

if test "x${domakecheck}" == "xyes"; then
  port -d test -D ${workdir}/${name} prefix=${location} build_arch=${architecture} workpath=${workdir}/${name}/work distpath=${workdir}/${name}/files
  if [[ $? != 0 ]]
  then
    toggleownmacportconf off
    echo "Make check failed for ${name}"
    return 1
  fi
fi
# Then destroot it in order to extract the globus dependend modules.
port destroot -D ${workdir}/${name} prefix=${location} build_arch=${architecture} workpath=${workdir}/${name}/work distpath=${workdir}/${name}/files
if [[ $? != 0 ]]
then
  toggleownmacportconf off
  echo "Make install failed for ${name}"
  return 1
fi

# Sanity check. Check if libraries are linked properly.
depslibs=`find ${name}/work/destroot/opt/local/nordugrid -name "*.dylib"`
if [[ -n ${depslibs} ]] && [[ `otool -L ${depslibs} | grep -v ${location} |\
                              grep -v /usr/lib |\
                              grep -c -v /System/Library` -ne 0 ]]
then
  toggleownmacportconf off
  echo "The ${name} package libraries are linked inconsistently."
  otool -L ${depslibs} | grep -v ${location} | grep -v /usr/lib | grep -v /System/Library
  return 1
fi

if test "x${makeglobus}" == "xyes"
then
  # Make directory for modules and move them there.
  mkdir -p ${workdir}/${arcglobusmoduledir}/destroot/${location}/lib/arc
  mv ${workdir}/${name}/work/destroot/${location}/lib/arc/lib{dmc{gridftp,rls},accARC0,mccgsi}.* ${workdir}/${arcglobusmoduledir}/destroot/${location}/lib/arc/.
fi

# Make meta package which should contain dependencies as well.
port mpkg -D ${workdir}/${name} prefix=${location} build_arch=${architecture} workpath=${workdir}/${name}/work
if [[ $? != 0 ]]
then
  toggleownmacportconf off
  echo "Creating meta-package ${name} failed"
  return 1
fi
toggleownmacportconf off

# Copy meta package for convenience.
cp -a ${workdir}/${name}/work/${name}-${version}.mpkg ${workdir}/.

return 0
}

function groupdependencypackages() {
# Group all required dependencies.
mkdir -p ${name}-${version}.mpkg/Contents/Packages/arcstandalone-dependencies.mpkg/Contents/{Packages,Resources}
cp -a ${name}-${version}.mpkg/Contents/PkgInfo ${name}-${version}.mpkg/Contents/Packages/arcstandalone-dependencies.mpkg/Contents/.
cat << EOF > ${name}-${version}.mpkg/Contents/Packages/arcstandalone-dependencies.mpkg/Contents/Resources/Description.plist
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>IFPkgDescriptionDescription</key>
  <string>This group of packages are required to be installed for ARC client to be functional.</string>
  <key>IFPkgDescriptionTitle</key>
  <string>External dependencies</string>
</dict>
</plist>
EOF

cat << EOF > ${name}-${version}.mpkg/Contents/Packages/arcstandalone-dependencies.mpkg/Contents/Info.plist
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">

<dict>
  <key>CFBundleGetInfoString</key>
  <string>arcstandalone-dependencies</string>
  <key>CFBundleIdentifier</key>
  <string>org.macports.mpkg.arcstandalone-dependencies</string>
  <key>CFBundleName</key>
  <string>arcstandalone-dependencies</string>
  <key>CFBundleShortVersionString</key>
  <string>0</string>
  <key>IFMajorVersion</key>
  <integer>0</integer>
  <key>IFMinorVersion</key>
  <integer>0</integer>
  <key>IFPkgFlagComponentDirectory</key>
  <string>./Contents/Packages</string>
  <key>IFPkgFlagPackageList</key>
  <array>
  </array>
  <key>IFPkgFormatVersion</key>
  <real>0.10000000149011612</real>
</dict>
</plist>
EOF

for package in ${deppackages[@]}
do
  insertpackage ${package} `port info --version -D ${package} | awk '{print $2}'` required arcstandalone-dependencies.mpkg || return 1
done

gsed -i "/<\/array>/i \\
\     <dict>\\
\       <key>IFPkgFlagPackageLocation</key>\\
\       <string>arcstandalone-dependencies.mpkg</string>\\
\       <key>IFPkgFlagPackageSelection</key>\\
\       <string>required</string>\\
\     </dict>
" ${name}-${version}.mpkg/Contents/Info.plist

return 0
}

function groupglobuspackages() {
# Group all Globus dependencies.
mkdir -p ${name}-${version}.mpkg/Contents/Packages/globus-dependencies.mpkg/Contents/{Packages,Resources}
cp -a ${name}-${version}.mpkg/Contents/PkgInfo ${name}-${version}.mpkg/Contents/Packages/globus-dependencies.mpkg/Contents/.
cat << EOF > ${name}-${version}.mpkg/Contents/Packages/globus-dependencies.mpkg/Contents/Resources/Description.plist
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>IFPkgDescriptionDescription</key>
  <string>The Globus packages are needed for Job Submission and Management against the Grid-Manager Computing Element.</string>
  <key>IFPkgDescriptionTitle</key>
  <string>Globus packages</string>
</dict>
</plist>
EOF

cat << EOF > ${name}-${version}.mpkg/Contents/Packages/globus-dependencies.mpkg/Contents/Info.plist
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">

<dict>
  <key>CFBundleGetInfoString</key>
  <string>arcstandalone-dependencies</string>
  <key>CFBundleIdentifier</key>
  <string>org.macports.mpkg.arcstandalone-dependencies</string>
  <key>CFBundleName</key>
  <string>arcstandalone-dependencies</string>
  <key>CFBundleShortVersionString</key>
  <string>0</string>
  <key>IFMajorVersion</key>
  <integer>0</integer>
  <key>IFMinorVersion</key>
  <integer>0</integer>
  <key>IFPkgFlagBackgroundAlignment</key>
  <string>bottomleft</string>
  <key>IFPkgFlagBackgroundScaling</key>
  <string>none</string>
  <key>IFPkgFlagComponentDirectory</key>
  <string>./Contents/Packages</string>
  <key>IFPkgFlagPackageList</key>
  <array>
  </array>
  <key>IFPkgFormatVersion</key>
  <real>0.10000000149011612</real>
</dict>
</plist>
EOF

for package in ${globuspkgs[@]}
do
  insertpackage globus-${package} `port info --version -D globus-${package} | awk '{print $2}'` required globus-dependencies.mpkg || return 1
done

gsed -i "/<\/array>/i \\
\     <dict>\\
\       <key>IFPkgFlagPackageLocation</key>\\
\       <string>globus-dependencies.mpkg</string>\\
\       <key>IFPkgFlagPackageSelection</key>\\
\       <string>selected</string>\\
\     </dict>
" ${name}-${version}.mpkg/Contents/Info.plist

return 0
}

function packagearcglobusmodule() {
# Package ARC globus modules.
mkdir -p ${arcglobusmoduledir}/${arcglobusmoduledir}-arcstandalone-${version}.pkg/Contents/Resources
mkbom ${arcglobusmoduledir}/destroot ${arcglobusmoduledir}/${arcglobusmoduledir}-arcstandalone-${version}.pkg/Contents/Archive.bom
pax -w ${arcglobusmoduledir}/destroot/opt -x cpio \
    -f ${arcglobusmoduledir}/${arcglobusmoduledir}-arcstandalone-${version}.pkg/Contents/Archive.pax \
    -s /${arcglobusmoduledir}\\\/destroot/./
gzip ${arcglobusmoduledir}/${arcglobusmoduledir}-arcstandalone-${version}.pkg/Contents/Archive.pax

cat << EOF > ${arcglobusmoduledir}/${arcglobusmoduledir}-arcstandalone-${version}.pkg/Contents/Resources/Description.plist
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>IFPkgDescriptionDescription</key>
  <string>Globus modules for the ARC client. This includes job and data management modules.</string>
  <key>IFPkgDescriptionTitle</key>
  <string>nordugrid-arc-plugins-globus</string>
</dict>
</plist>
EOF

cat << EOF > ${arcglobusmoduledir}/${arcglobusmoduledir}-arcstandalone-${version}.pkg/Contents/Info.plist
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleGetInfoString</key>
  <string>nordugrid-arc-plugins-globus ${version}</string>
  <key>CFBundleIdentifier</key>
  <string>nordugrid-arc-plugins-globus</string>
  <key>CFBundleName</key>
  <string>nordugrid-arc-plugins-globus ${version}</string>
  <key>CFBundleShortVersionString</key>
  <string>${version}</string>
  <key>IFMajorVersion</key>
  <integer>0</integer>
  <key>IFMinorVersion</key>
  <integer>0</integer>
  <key>IFPkgFlagAllowBackRev</key>
  <true/>
  <key>IFPkgFlagAuthorizationAction</key>
  <string>RootAuthorization</string>
  <key>IFPkgFlagDefaultLocation</key>
  <string>/</string>
  <key>IFPkgFlagFollowLinks</key>
  <true/>
  <key>IFPkgFlagInstallFat</key>
  <false/>
  <key>IFPkgFlagInstalledSize</key>
  <integer>648</integer>
  <key>IFPkgFlagIsRequired</key>
  <false/>
  <key>IFPkgFlagOverwritePermissions</key>
  <false/>
  <key>IFPkgFlagRelocatable</key>
  <false/>
  <key>IFPkgFlagRestartAction</key>
  <string>NoRestart</string>
  <key>IFPkgFlagRootVolumeOnly</key>
  <true/>
  <key>IFPkgFlagUpdateInstalledLanguages</key>
  <false/>
  <key>IFPkgFormatVersion</key>
  <real>0.10000000149011612</real>
</dict>
</plist>
EOF

echo -n "pmkrpkg1" >  ${arcglobusmoduledir}/${arcglobusmoduledir}-arcstandalone-${version}.pkg/Contents/PkgInfo
echo    "major: 1" >  ${arcglobusmoduledir}/${arcglobusmoduledir}-arcstandalone-${version}.pkg/Contents/Resources/package_version
echo -n "minor: 1" >> ${arcglobusmoduledir}/${arcglobusmoduledir}-arcstandalone-${version}.pkg/Contents/Resources/package_version

insertpackage ${arcglobusmoduledir} ${version} required globus-dependencies.mpkg || return 1

return 0
}

function packagecertificates() {
toggleownmacportconf on
# Include igtf-certificates in the standalone package.
port pkg igtf-certificates prefix=${location} build_arch=${architecture} workpath=${workdir}/igtf-certificates/work
toggleownmacportconf off

igtfversion=`port info --version igtf-certificates | awk '{ print $2 }'`

mv -f ${workdir}/igtf-certificates/work/igtf-certificates-${igtfversion}.pkg \
      ${workdir}/igtf-certificates/igtf-certificates-arcstandalone-${igtfversion}.pkg

if [[ $? != 0 ]]; then
  echo "igtf-certificates package not found"
  return 1
fi

insertpackage igtf-certificates ${igtfversion} selected || return 1

return 0
}

function completepackage() {
# Add PATHs to environment by using postinstall script. Copy ReadMe to location. Set to executable.
cat << EEOOFF > ${name}-${version}.mpkg/Contents/Resources/postinstall
#!/bin/bash
cat << EOF > /etc/paths.d/nordugrid-arc-standalone
${location}/bin
EOF

export PATH=\$PATH:${location}/bin

cp \${PACKAGE_PATH}/Contents/Resources/ReadMe ${location}/.

if test -f /etc/profile && test ! `grep -q GLOBUS_LOCATION /etc/profile` ; then
  echo "export GLOBUS_LOCATION=${location}" >> /etc/profile
fi
EEOOFF

chmod +x ${name}-${version}.mpkg/Contents/Resources/postinstall

cp ${workdir}/${name}/work/${source//.tar.gz}/LICENSE \
   ${name}-${version}.mpkg/Contents/Resources/License

cat << EOF > ${name}-${version}.mpkg/Contents/Resources/ReadMe
You need to do the following steps after installation of ARC
------------------------------------------------------------

Install Grid certificate and private key:

  Copy your usercert.pem file to: \$HOME/.globus/usercert.pem
  Copy your userkey.pem  file to: \$HOME/.globus/userkey.pem


Other information
-----------------

Default client.conf, jobs.xml directory location (these directories are hidden by default):

  \$HOME/.arc


Uninstalling this package
-------------------------

To uninstall this package simply remove the '${location}' directory and the file '/etc/paths.d/nordugrid-arc-nox-standalone'.
Additionally user configuration files might exist in the \$HOME/.arc directory, which can safely be removed.
EOF

# Remove MacPorts background and use own background.
wget -q http://www.nordugrid.org/images/ng-logo.png -O ${name}-${version}.mpkg/Contents/Resources/background

if [[ $? != 0 ]]; then
  echo "WARNING: Unable to fetch NG-logo"
else 
  rm -f ${name}-${version}.mpkg/Contents/Resources/background.tiff

  # Put logo in bottom-left corner, and do not scale it.
  gsed -i \
    -e "/<key>IFPkgFlagComponentDirectory<\/key>/i \\
\  <key>IFPkgFlagBackgroundAlignment</key>\\
\  <string>bottomleft</string>\\
\  <key>IFPkgFlagBackgroundScaling</key>\\
\  <string>none</string>\\
" \
    -e "/<string>${name}-${version}.pkg<\/string>/,/<string>selected<\/string>/s/selected/required/" \
    ${name}-${version}.mpkg/Contents/Info.plist
fi


return 0
}

function compresspackage() {
# Compress package
zip -qr ${name}-${version}.mpkg.zip ${name}-${version}.mpkg
if [[ $? != 0 ]]; then
  echo "Unable to compress package."
  return 1
fi

rm -rf ${name}-${version}.mpkg
mv ${name}-${version}.mpkg.zip ${basedir}/.
if [[ $? != 0 ]]; then
  echo "Unable to move package \"${name}-${version}.mpkg.zip\" to \"${basedir}/.\""
  return 1
fi

return 0
}

function cleanup() {
toggleownmacportconf on

# Clean package.
port -q clean --all -D ${workdir}/${name}
port -q clean --all igtf-certificates

# Remove arcstandalone packages and delete temporary directories.
for package in ${deppackages[@]}
do
  port -q uninstall -D ${workdir}/${package}
  rm -rf ${package}
done
for package in ${globuspkgs[@]}
do
  port -q uninstall globus-${package}-arcstandalone
  rm -rf globus-${package}
done
port -q uninstall grid-packaging-tools-arcstandalone
rm -rf grid-packaging-tools
port -q uninstall globus-core-arcstandalone
rm -rf globus-core

toggleownmacportconf off

rm -rf ${location}/*

cd ${basedir}
rm -rf ${workdir}

return 0
}

function build_standalone() {

echo "Building ARC standalone for Mac OS X with the following options:"
echo "Name: $name"
echo "Version: $version"
echo "Channel: $type"
echo "Install location: $location"
echo "Architecture: $architecture"
echo "Build globus module: $makeglobus"

initialise || return 1

echo "Working directory: $workdir"

requiredpackagescheck || return 1
fetchsource || return 1
createportfile || return 1

makedependencypackages || return 1
if test "x${makeglobus}" == "xyes"
then
makeglobuspackages || return 1
fi

makearcmetapackage || return 1

groupdependencypackages || return 1
if test "x${makeglobus}" == "xyes"
then
groupglobuspackages || return 1
packagearcglobusmodule || return 1
fi
packagecertificates || return 1
completepackage || return 1
compresspackage || return 1
cleanup || return 1

echo "Creating ${name}-standalone finished successfully"
}


if test "x${BUILD_ARC_INTERACTIVE}" != "xyes"; then
if test $# -gt 4; then
  echo "0 to 4 arguments needed."
  echo "${0} [type] [version] [build globus] [perform make check]"
  exit 1
fi

# First argument is type which should be one of (releases, testing, experimental, nightlies)
if test "x${1}" != "xreleases" && test "x${1}" != "xtesting" && test "x${1}" != "xexperimental"; then
  type="nightlies"
else
  type=${1}
fi

if test "x${type}" != "xnightlies" && test $# == 1
then
  echo "2nd argument (version) must be specified for type \"${type}\"."
  exit 1
fi

if test "x${2}" != "x"; then
  version=${2}
fi

test $# -ge 3 && test "x${3}" == "xno" && makeglobus="no"
test $# == 4 && test "x${4}" == "xyes" && domakecheck="yes"

else
type="nightlies"
fi

test "x${BUILD_ARC_INTERACTIVE}" != "xyes" && build_standalone
