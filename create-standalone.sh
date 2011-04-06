#!/bin/bash
#
# This script creates a Mac OS X NorduGrid ARC standalone package.
# Usage: create-standalone.sh <type> [version] [build globus]
# Relies on the files in the repository, and must be executed here.
#
# TODO:
# * Support for nightlies
# * Upload package to download.nordugrid.org
# * Modify ReadMe file
# * Add a 'Finish Up' entry in the installer
# * Make the script independent on run-time location.

if test $# != 1 && test $# != 2 && test $# != 3
then
  echo "1 to 3 arguments needed."
  echo "${0} <type> [version] [build globus]"
  exit 1
fi

# Second argument is type which should be one of (releases (default), testing, experimental).
if test ${1} != "releases" && test ${1} != "testing" && test ${1} != "experimental" && test ${1} != "nightlies"
then
  echo "First argument must be one of \"releases\", \"testing\", \"experimental\" or \"nightlies\"."
  exit 1
fi
type=${1}

if test ${type} != "nightlies" && test $# == 1
then
  echo "2nd argument (version) must be specified for type \"${type}\"."
  exit 1
fi

makeglobus="no"
test $# == 3 && test "x${3}" == "xyes" && makeglobus="yes"

architecture=x86_64


basedir=`pwd`
workdir=arcstandalone-workdir
rm -rf ${workdir}
mkdir ${workdir}
cd ${workdir}

# Install package to the specified location. Note that the specified location should be a path used exclusively for the standalone.
location=/opt/local/nordugrid

name=nordugrid-arc-standalone
version=$2

arcglobusmoduledir=globus-plugins

# The metapackage should contain the following packages (order matters!):
deppackages=(zlib openssl libiconv libxml2 gettext libsigcxx2 perl5.8 perl5 python_select glib2 glibmm libtool)

# The following globus packages are needed for a working ARC0 middleware module. Order matters.
globuspkgs=(libtool common callout openssl gsi-openssl-error gsi-proxy-ssl openssl-module \
            gsi-cert-utils gsi-sysconfig gsi-callback gsi-credential gsi-proxy-core \
            gssapi-gsi gss-assist gssapi-error xio xio-gsi-driver io xio-popen-driver \
            ftp-control ftp-client rls-client)

function insertpackage() {
pkgname=${1}
pkgversion=${2}
pkgdir=${name}-${version}.mpkg/Contents/

if [[ "x${4}x" != "xx" ]]; then
  pkgdir=${pkgdir}/Packages/${4}/Contents/
fi
rm -rf ${pkgdir}/Packages/${pkgname}-${pkgversion}.pkg
mv -f ${pkgname}/${pkgname}-${pkgversion}.pkg ${pkgdir}/Packages/.
sed -i .old "/<\/array>/i \\
\     <dict>\\
\       <key>IFPkgFlagPackageLocation</key>\\
\       <string>${pkgname}-${pkgversion}.pkg</string>\\
\       <key>IFPkgFlagPackageSelection</key>\\
\       <string>${3}</string>\\
\     </dict>
" ${pkgdir}/Info.plist
}

function makedeppackage() {
pkgname=${1}
rm -rf ${pkgname}-arcstandalone
mkdir ${pkgname}-arcstandalone
# Modify Portfile  to our purpose.
port cat ${pkgname} | sed -e :a -e '$!N;s/[[:space:]]*\\\n[[:space:]]*/ /;ta' \
                    | sed -e "s/\${name}/${pkgname}/g" \
                    | sed -e "s/\(name[[:space:]]*${pkgname}\)/\1-arcstandalone/" \
                    | sed -e "/^depends_lib/d" \
                    | sed -e "/^archcheck.files/d" \
                    | sed -e "s/^\(master_sites[[:space:]]*gnu\)/\1:${pkgname}/" > ${pkgname}-arcstandalone/Portfile

sed -i .old "/checksums/i \\
destroot.violate_mtree      yes\\
" ${pkgname}-arcstandalone/Portfile

if [[ ${pkgname} = "glibmm" ]]
then
  sed -i .old -e "
                  /^checksums/a \\
                  \\
                  configure.env PKG_CONFIG_LIBDIR=${location}/lib/pkgconfig
                  " ${pkgname}-arcstandalone/Portfile
fi

# Set distname so source can be fetched.
sed -i .old "
             /^[[:space:]]*version[[:space:]]/a \\
             distname ${pkgname}-\${version}\\
             " ${pkgname}-arcstandalone/Portfile
# Make link to patch files.
[[ -d `port dir ${pkgname}`/files ]] && ln -s `port dir ${pkgname}`/files ${pkgname}-arcstandalone/files
# Wait 1 second before creating package to avoid MacPorts complaining about files in future.
sleep 1
# Make a package.
port pkg -D ${pkgname}-arcstandalone prefix=${location} build_arch=${architecture}
if [[ $? -ne 0 ]]
then
  echo "Unable to make package ${pkgname}"
  exit 1
fi

# Move package, so it is not deleted.
pkgversion=`port info --version -D ${pkgname}-arcstandalone | awk '{ print $2 }'`
mv -f ${pkgname}-arcstandalone/work/${pkgname}-arcstandalone-${pkgversion}.pkg ${pkgname}-arcstandalone/.
mv -f ${pkgname}-arcstandalone/${pkgname}-arcstandalone-${pkgversion}.pkg/Contents/Resources/English.lproj/Description.plist \
      ${pkgname}-arcstandalone/${pkgname}-arcstandalone-${pkgversion}.pkg/Contents/Resources/.
rm -rf ${pkgname}-arcstandalone/${pkgname}-arcstandalone-${pkgversion}.pkg/Contents/Resources/English.lproj

description=`port info --long_description -D ${pkgname}-arcstandalone | sed "s/^long_description: //"`
description=${description//\//\\\/}

sed -i .old "s/<string><\/string>/<string>${description}<\/string>/" \
  ${pkgname}-arcstandalone/${pkgname}-arcstandalone-${pkgversion}.pkg/Contents/Resources/Description.plist

# Install package since others packages might depend on it.
port install -D ${pkgname}-arcstandalone prefix=${location} build_arch=${architecture}

# Sanity check. Check if libraries are linked properly.
depslibs=`port contents -D ${pkgname}-arcstandalone | grep ${location} | grep dylib`
if [[ -n ${depslibs} ]] && [[ `otool -L ${depslibs} | grep -v ${location} |\
                              grep -v /usr/lib |\
                              grep -c -v /System/Library` -ne 0 ]]
then
  echo "The ${pkgname} package libraries are linked inconsistently."
  otool -L ${depslibs} | grep -v ${location} | grep -v /usr/lib | grep -v /System/Library
  exit 1
fi

return 0
}

function makeglobuspackage() {
pkgname=${1}
portdir=${2-net}

if [[ "${pkgname}" != "grid-packaging-tools" ]]; then
  pkgname=globus-${pkgname}
fi

rm -rf ${pkgname}-arcstandalone
mkdir ${pkgname}-arcstandalone
# Modify Portfile  to our purpose.
port cat -D ${basedir}/${portdir}/${pkgname} \
  | sed -e :a -e '$!N;s/[[:space:]]*\\\n[[:space:]]*/ /;ta' \
  | sed -e "s/\${name}/${pkgname}/g" \
  | sed -e "s/\$name/${pkgname}/g" \
  | sed -e "s/\(name[[:space:]]*${pkgname}\)/\1-arcstandalone/" \
  | sed -e "/^depends/d" \
  | sed -e "s@\${prefix}/share/libtool@/opt/local/share/libtool@g" \
  | sed -e "/^archcheck.files/d" > ${pkgname}-arcstandalone/Portfile

sed -i .old "/checksums/i \\
destroot.violate_mtree      yes\\
" ${pkgname}-arcstandalone/Portfile

# Make link to patch files.
[[ -d `port dir -D ${basedir}/${portdir}/${pkgname}`/files ]] && ln -s `port dir -D ${basedir}/${portdir}/${pkgname}`/files ${pkgname}-arcstandalone/files

if [[ "${pkgname}" == "grid-packaging-tools" ]] || [[ "${pkgname}" == "globus-core" ]];
then
  port install -D ${pkgname}-arcstandalone prefix=${location} build_arch=${architecture}
  if [[ $? -ne 0 ]]
  then
    echo "Unable to make package ${pkgname}"
    exit 1
  fi

  return
fi

# Make a package.
port pkg -D ${pkgname}-arcstandalone prefix=${location} build_arch=${architecture}
if [[ $? -ne 0 ]]
then
  echo "Unable to make package ${pkgname}"
  exit 1
fi

# Move package, so it is not deleted.
pkgversion=`port info --version -D ${pkgname}-arcstandalone | awk '{ print $2 }'`
mv -f ${pkgname}-arcstandalone/work/${pkgname}-arcstandalone-${pkgversion}.pkg ${pkgname}-arcstandalone/.
mv -f ${pkgname}-arcstandalone/${pkgname}-arcstandalone-${pkgversion}.pkg/Contents/Resources/English.lproj/Description.plist \
      ${pkgname}-arcstandalone/${pkgname}-arcstandalone-${pkgversion}.pkg/Contents/Resources/.
rm -rf ${pkgname}-arcstandalone/${pkgname}-arcstandalone-${pkgversion}.pkg/Contents/Resources/English.lproj

description=`port info --long_description -D ${pkgname}-arcstandalone | sed "s/^long_description: //"`
description=${description//\//\\\/}

sed -i .old "s/<string><\/string>/<string>${description}<\/string>/" \
  ${pkgname}-arcstandalone/${pkgname}-arcstandalone-${pkgversion}.pkg/Contents/Resources/Description.plist

# Install package since others packages might depend on it.
port install -D ${pkgname}-arcstandalone prefix=${location} build_arch=${architecture}

# Sanity check. Check if libraries are linked properly.
depslibs=`port contents -D ${pkgname}-arcstandalone | grep ${location} | grep dylib`
if [[ -n ${depslibs} ]] && [[ `otool -L ${depslibs} | grep -v ${location} |\
                              grep -v /usr/lib |\
                              grep -c -v /System/Library` -ne 0 ]]
then
  echo "The ${pkgname} package libraries are linked inconsistently."
  otool -L ${depslibs} | grep -v ${location} | grep -v /usr/lib | grep -v /System/Library
  exit 1
fi

return 0
}

function requiredpackagescheck() {
# The following packages are required to be installed to build the stand-alone package.
requiredpkgs=(gperf pkgconfig autoconf automake nordugrid-arc-client doxygen p5-archive-tar perl5)
pkgsneeded=
installedports=`port installed`
for package in ${requiredpkgs[@]}
do
  [[ `echo $installedports | grep -c $package` -eq 0 ]] && pkgsneeded="$pkgsneeded $package"
done

if test "x${pkgsneeded}x" != "xx"
then
  echo "The following packages are required to build the stand-alone:"
  echo $pkgsneeded
  echo "Please install them."
  exit 1
fi
}

function fetchsource() {
# Source need to be downloaded to be able to calculate checksums. Remove old source first.
rm -rf ${basedir}/${name}/files
mkdir ${basedir}/${name}/files

if test ${type} == "nightlies"
then
  export GLOBUS_LOCATION=/opt/local
  date=`date +%F`
  source=`arcls gsiftp://lscf.nbi.dk/nightlies/nordugrid-arc/trunk/${date}/src | grep "nordugrid-arc-[0-9]\+.tar.gz"`
  
  arccp gsiftp://lscf.nbi.dk/nightlies/nordugrid-arc/trunk/${date}/src/${source} ${basedir}/${name}/files/${source}
  if [[ $? != 0 ]]
  then
    echo "Unable to fetch source."
    exit 1
  else
    echo "Source successfully fetched"
    exit 0
  fi
else
  source=nordugrid-arc-${version}.tar.gz
  arccp http://download.nordugrid.org/software/nordugrid-arc/${type}/${version}/src/${source} ${basedir}/${name}/files/${source}
fi

if [[ $? != 0 ]]
then
  echo "Unable to fetch source."
  exit 1
fi
}

function calculatechecksums() {
# Calculate and insert checksums and insert version.
md5=`md5 ${basedir}/${name}/files/${source} | awk '{ print $NF }'`
sha1=`openssl sha1 ${basedir}/${name}/files/${source} | awk '{ print $NF }'`
rmd160=`openssl rmd160 ${basedir}/${name}/files/${source} | awk '{ print $NF }'`
sed -e "s/__VERSION__/${version}/" \
    -e "s/__MD5__/${md5}/" \
    -e "s/__SHA1__/${sha1}/" \
    -e "s/__RMD160__/${rmd160}/" ${basedir}/${name}/Portfile.in > ${basedir}/${name}/Portfile
}

function makedependencypackages() {
for package in ${deppackages[@]}
do
  makedeppackage $package
done
}

function makeglobuspackages() {
# Make globus packages. grid-packaging-tools and globus-core is needed to build the other packages.
makeglobuspackage grid-packaging-tools devel
makeglobuspackage core devel

for package in ${globuspkgs[@]}
do
  makeglobuspackage $package
done
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
  insertpackage ${package}-arcstandalone `port info --version -D ${package}-arcstandalone | awk '{print $2}'` required arcstandalone-dependencies.mpkg
done

sed -i .old "/<\/array>/i \\
\     <dict>\\
\       <key>IFPkgFlagPackageLocation</key>\\
\       <string>arcstandalone-dependencies.mpkg</string>\\
\       <key>IFPkgFlagPackageSelection</key>\\
\       <string>required</string>\\
\     </dict>
" ${name}-${version}.mpkg/Contents/Info.plist
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
  insertpackage globus-${package}-arcstandalone `port info --version -D globus-${package}-arcstandalone | awk '{print $2}'` required globus-dependencies.mpkg
done

sed -i .old "/<\/array>/i \\
\     <dict>\\
\       <key>IFPkgFlagPackageLocation</key>\\
\       <string>globus-dependencies.mpkg</string>\\
\       <key>IFPkgFlagPackageSelection</key>\\
\       <string>selected</string>\\
\     </dict>
" ${name}-${version}.mpkg/Contents/Info.plist
}

function packagearcglobusmodule() {
# Package ARC globus modules.
mkdir -p ${arcglobusmoduledir}/${arcglobusmoduledir}-${version}.pkg/Contents/Resources
mkbom ${arcglobusmoduledir}/destroot ${arcglobusmoduledir}/${arcglobusmoduledir}-${version}.pkg/Contents/Archive.bom
pax -w ${arcglobusmoduledir}/destroot/opt -x cpio \
    -f ${arcglobusmoduledir}/${arcglobusmoduledir}-${version}.pkg/Contents/Archive.pax \
    -s /${arcglobusmoduledir}\\\/destroot/./
gzip ${arcglobusmoduledir}/${arcglobusmoduledir}-${version}.pkg/Contents/Archive.pax

cat << EOF > ${arcglobusmoduledir}/${arcglobusmoduledir}-${version}.pkg/Contents/Resources/Description.plist
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

cat << EOF > ${arcglobusmoduledir}/${arcglobusmoduledir}-${version}.pkg/Contents/Info.plist
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleGetInfoString</key>
  <string>nordugrid-arc-plugins-globus ${version}</string>
  <key>CFBundleIdentifier</key>
  <string>nordugrid-arc-plugins-globus</string>
  <key>CFBundleName</key>
  <string>zlib-arcstandalone</string>
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

echo -n "pmkrpkg1" >  ${arcglobusmoduledir}/${arcglobusmoduledir}-${version}.pkg/Contents/PkgInfo
echo    "major: 1" >  ${arcglobusmoduledir}/${arcglobusmoduledir}-${version}.pkg/Contents/Resources/package_version
echo -n "minor: 1" >> ${arcglobusmoduledir}/${arcglobusmoduledir}-${version}.pkg/Contents/Resources/package_version

insertpackage ${arcglobusmoduledir} ${version} required globus-dependencies.mpkg
}

function packagecertificates() {
# Include igtf-certificates in the standalone package.
port pkg -D ${basedir}/igtf-certificates prefix=${location} build_arch=${architecture}
mkdir -p igtf-certificates
mv -f ${basedir}/igtf-certificates/work/igtf-certificates-`port info --version -D ${basedir}/igtf-certificates | awk '{ print $2 }'`.pkg \
      igtf-certificates/.
insertpackage igtf-certificates `port info --version -D ${basedir}/igtf-certificates | awk '{ print $2 }'` selected
port clean --all -D ${basedir}/igtf-certificates
}

function cleanup() {
# Clean package.
port clean --all -D ${basedir}/${name}
port clean --all -D ${basedir}/igtf-certificates

# Remove arcstandalone packages and delete temporary directories.
for package in ${deppackages[@]}
do
  port uninstall ${package}-arcstandalone
  rm -rf ${package}-arcstandalone
done
for package in ${globuspkgs[@]}
do
  port uninstall globus-${package}-arcstandalone
  rm -rf globus-${package}-arcstandalone
done
port uninstall grid-packaging-tools-arcstandalone
rm -rf grid-packaging-tools-arcstandalone
port uninstall globus-core-arcstandalone
rm -rf globus-core-arcstandalone

# Remove temporary files.
rm -f `find ${name}-${version}.mpkg/ -name "*.old"`
}

function compresspackage() {
# Compress package
zip -qr ${name}-${version}.mpkg.zip ${name}-${version}.mpkg
if [[ $? -eq 0 ]]
then
  rm -rf ${name}-${version}.mpkg
fi
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
EEOOFF

chmod +x ${name}-${version}.mpkg/Contents/Resources/postinstall

cp ${basedir}/${name}/work/nordugrid-arc-${version}/LICENSE \
   ${name}-${version}.mpkg/Contents/Resources/License
sed "s@__LOCATION__@${location}@g" ${basedir}/ReadMe > ${name}-${version}.mpkg/Contents/Resources/ReadMe

# Remove MacPorts background and use own background.
rm -f ${name}-${version}.mpkg/Contents/Resources/background.tiff
cp ${basedir}/logo-ng-shaded.png \
   ${name}-${version}.mpkg/Contents/Resources/background

# Put logo in bottom-left corner, and do not scale it.
sed -i .old \
  -e "/<key>IFPkgFlagComponentDirectory<\/key>/i \\
\  <key>IFPkgFlagBackgroundAlignment</key>\\
\  <string>bottomleft</string>\\
\  <key>IFPkgFlagBackgroundScaling</key>\\
\  <string>none</string>\\
" \
  -e "/<string>${name}-${version}.pkg<\/string>/,/<string>selected<\/string>/s/selected/required/" \
  ${name}-${version}.mpkg/Contents/Info.plist
}


requiredpackagescheck
fetchsource
calculatechecksums
makedependencypackages
if test "x${makeglobus}" == "xyes"
then
makeglobuspackages
fi

# Create the Nordugrid ARC stand-alone package.
# First destroot the stand-alone in order to extract the globus dependend modules.
port destroot -D ${basedir}/${name} prefix=${location} build_arch=${architecture}
if [[ $? != 0 ]]
then
  echo "Building ${name} failed"
  exit 1
fi

if test "x${makeglobus}" == "xyes"
then
# Make directory for modules and move them there.
mkdir -p ${arcglobusmoduledir}/destroot/${location}/lib/arc
mv `port work -D ${basedir}/${name}`/destroot/${location}/lib/arc/lib{dmc{gridftp,rls},accARC0,mccgsi}.* ${arcglobusmoduledir}/destroot/${location}/lib/arc/.
fi
# Make meta package which should contain dependencies as well.
port mpkg -D ${basedir}/${name} prefix=${location} build_arch=${architecture}
if [[ $? != 0 ]]
then
  echo "Creating meta-package ${name} failed"
  exit 1
fi
# Copy meta package for convenience.
cp -a `port work -D ${basedir}/${name}`/${name}-${version}.mpkg .

groupdependencypackages
if test "x${makeglobus}" == "xyes"
then
groupglobuspackages
packagearcglobusmodule
fi
packagecertificates
completepackage
cleanup
compresspackage

cd ${basedir}
mv ${workdir}/${name}-${version}.mpkg.zip .
rm -rf ${workdir}
