if [ -f /etc/nsscache.conf.rpmsave ]; then
  cp -a /etc/nsscache.conf /etc/nsscache.conf.rpmnew
  mv -f /etc/nsscache.conf.rpmsave /etc/nsscache.conf
fi
