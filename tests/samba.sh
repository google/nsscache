#!/bin/bash -eux

export DEBIAN_FRONTEND=noninteractive

apt-get update

PACKAGES=(
'samba'
'samba-dsdb-modules'
'samba-vfs-modules'
'winbind'
'heimdal-clients'
)

# Install needed packages
for package in "${PACKAGES[@]}"; do
    apt-get -y install "$package"
done

# Samba must not be running during the provisioning
service smbd stop
service nmbd stop 
service winbind stop
service samba-ad-dc stop

# Domain provision
rm -fr /etc/samba/smb.conf
/usr/bin/samba-tool domain provision --realm=LOCAL.DOMAIN --domain=LOCAL --server-role=dc --dns-backend=SAMBA_INTERNAL --adminpass='4dm1n_s3cr36_v3ry_c0mpl3x' --use-rfc2307 -d 1

# Start samba-ad-dc service only
rm -fr /etc/systemd/system/samba-ad-dc.service
service samba-ad-dc start

# Add users and groups
/usr/bin/samba-tool user create user1 --use-username-as-cn --surname=Test1 --given-name=User1 --random-password
/usr/bin/samba-tool user create user2 --use-username-as-cn --surname=Test2 --given-name=User2 --random-password
/usr/bin/samba-tool user create user3 --use-username-as-cn --surname=Test3 --given-name=User3 --random-password
/usr/bin/samba-tool user create user4 --use-username-as-cn --surname=Test4 --given-name=User4 --random-password
/usr/bin/samba-tool user create user5 --use-username-as-cn --surname=Test5 --given-name=User5 --random-password

# Add some groups
/usr/bin/samba-tool group add IT
/usr/bin/samba-tool group add Admins
/usr/bin/samba-tool group add Devs
/usr/bin/samba-tool group add DevOps

# Create members
/usr/bin/samba-tool group addmembers IT Admins,Devs,DevOps,user1
/usr/bin/samba-tool group addmembers Admins user2,user3
/usr/bin/samba-tool group addmembers Devs user4
/usr/bin/samba-tool group addmembers DevOps user5

# Add AD certificate
echo -n | openssl s_client -connect localhost:636 | sed -ne '/-BEGIN CERTIFICATE-/,/-END CERTIFICATE-/p' > /usr/local/share/ca-certificates/ad.crt
update-ca-certificates

# Add cache to nsswitch
cat > '/etc/nsswitch.conf' << EOF
passwd:         files cache
group:          files cache
shadow:         files cache
gshadow:        files

hosts:          files dns
networks:       files

protocols:      db files
services:       db files
ethers:         db files
rpc:            db files

netgroup:       nis
EOF
