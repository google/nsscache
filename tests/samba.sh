#!/bin/bash -eux

export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get upgrade -y
apt-get dist-upgrade -y

PACKAGES=(
'samba'
'winbind'
'heimdal-clients'
)

# Install needed packages
for package in "${PACKAGES[@]}"; do
    apt-get -y install "$package"
done

# Samba must not be running during the provisioning
rm -fr /etc/systemd/system/samba-ad-dc.service
systemctl daemon-reload
systemctl stop samba-ad-dc.service smbd.service nmbd.service winbind.service
systemctl disable samba-ad-dc.service smbd.service nmbd.service winbind.service

# Domain provision
echo '' > /etc/samba/smb.conf && samba-tool domain provision --realm=LOCAL.DOMAIN --domain=LOCAL --server-role='dc' --dns-backend='SAMBA_INTERNAL' --option 'dns forwarder'='127.0.0.1' --adminpass='4dm1n_s3cr36_v3ry_c0mpl3x' --use-rfc2307 -d 1

# Kerberos settings
rm -fr /etc/krb5.conf
cp /var/lib/samba/private/krb5.conf /etc/

# Start samba-ad-dc service only
rm -fr /etc/systemd/system/samba-ad-dc.service
systemctl daemon-reload
systemctl start samba-ad-dc.service
systemctl enable samba-ad-dc.service

# Request a kerberos ticket
cat > '/root/.kinit' << EOF
4dm1n_s3cr36_v3ry_c0mpl3x
EOF

kinit --password-file="/root/.kinit" administrator@LOCAL.DOMAIN

# Add users and groups
samba-tool user create user1 --use-username-as-cn --surname=Test1 --given-name=User1 --random-password
samba-tool user create user2 --use-username-as-cn --surname=Test2 --given-name=User2 --random-password
samba-tool user create user3 --use-username-as-cn --surname=Test3 --given-name=User3 --random-password
samba-tool user create user4 --use-username-as-cn --surname=Test4 --given-name=User4 --random-password

# Add some groups
samba-tool group add IT
samba-tool group add Admins
samba-tool group add Devs
samba-tool group add DevOps

# Create members
/usr/bin/samba-tool group addmembers IT Admins,Devs,DevOps,user1
/usr/bin/samba-tool group addmembers Admins user2
/usr/bin/samba-tool group addmembers Devs user3
/usr/bin/samba-tool group addmembers DevOps user4
