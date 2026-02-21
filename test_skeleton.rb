require 'unicode/confusable'
puts Unicode::Confusable.skeleton('agnt.p0d') == Unicode::Confusable.skeleton('agnt.pod')
puts Unicode::Confusable.skeleton('0') == Unicode::Confusable.skeleton('o')
puts Unicode::Confusable.skeleton('a.g.n.t.p.o.d') == Unicode::Confusable.skeleton('agntpod')
