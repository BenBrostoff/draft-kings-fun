from abc import ABC, abstractmethod


def _iterableify(x):
    if isinstance(x, (str)):
        return [x]
    return x


class LineupConstraints(object):
    def __init__(self):
        self._constraints = []
        self._banned = set()
        self._locked = set()
        self._banned_for_exposure = set()
        self._locked_for_exposure = set()

    def __iter__(self):
        return ConstraintIterator(self._constraints)

    def __len__(self):
        return len(self._constraints) + \
               len(self._locked) + \
               len(self._banned) + \
               len(self._locked_for_exposure) + \
               len(self._banned_for_exposure)

    def __repr__(self):
        constraints = ', '.join([repr(c) for c in self._constraints])
        lcs = 'LineupConstraintSet: {}'.format(constraints)
        b1 = '<Banned: {!r}>'.format(self._banned)
        l1 = '<Locked: {!r}>'.format(self._locked)
        b2 = '<Banned for exposure: {!r}>'.format(self._banned_for_exposure)
        l2 = '<Locked for exposure: {!r}>'.format(self._locked_for_exposure)
        return '<{}, {}, {}, {}, {}>'.format(lcs, b1, l1, b2, l2)

    def __str__(self):
        return '\n'.join(str(c) for c in self._constraints) + \
               'BANNED:\n' + \
               '\n'.join(
                   ['\t{}'.format(str(p) for p in self._banned)]
                   ) + \
               'LOCKED:\n' + \
               '\n'.join(
                   ['\t{}'.format(str(p) for p in self._locked)]
                   ) + \
               'BANNED FOR EXPOSURE:\n' + \
               '\n'.join(
                   ['\t{}'.format(str(p) for p in self._banned_for_exposure)]
                   ) + \
               'LOCKED FOR EXPOSURE:\n' + \
               '\n'.join(
                   ['\t{}'.format(str(p) for p in self._locked_for_exposure)]
                   )

    def __eq__(self, constraintset):
        if len(self._constraints) != len(constraintset._constraints):
            return False

        if set(self._constraints) != set(constraintset._constraints):
            return False

        if self._locked != constraintset._locked:
            return False

        if self._banned != constraintset._banned:
            return False

        if self._locked_for_exposure != constraintset._locked_for_exposure:
            return False

        if self._banned_for_exposure != constraintset._banned_for_exposure:
            return False

        return True

    def __contains__(self, player):
        if player in self._locked:
            return True

        if player in self._banned:
            return True

        if player in self._locked_for_exposure:
            return True

        if player in self._banned_for_exposure:
            return True

        for c in self._constraints:
            if isinstance(c, PlayerGroupConstraint):
                if player in c.players:
                    return True

        return False

    # TODO this will create conflicts with exposure code, maybe create
    # a new class for players locked/banned by the exposure code?
    def _check_conflicts(self, constraint):
        if isinstance(constraint, PlayerGroupConstraint):
            for p in constraint.players:
                if p in self._locked or p in self._banned:
                    raise ConstraintConflictException(
                        'Ban/lock constraint for {} already exists'.format(p)
                    )

    def _add(self, constraint):
        self._check_conflicts(constraint)

        if constraint not in self._constraints:
            self._constraints.append(constraint)
        else:
            raise ConstraintConflictException('Duplicate constraint')

    def is_banned(self, player):
        return player in self._banned

    def is_locked(self, player):
        return player in self._locked

    def add_group_constraint(self, players, bound):
        self._add(PlayerGroupConstraint(players, bound))

    def ban(self, players, for_exposure=False):
        _players = _iterableify(players)

        if len(_players) == 0:
            raise ConstraintException('Empty ban group')

        for p in _players:
            if p in self:
                raise ConstraintConflictException(
                    '{} exists in another constraint'.format(p)
                )

        if for_exposure:
            self._banned_for_exposure.update(_players)
        else:
            self._banned.update(_players)

    def lock(self, players, for_exposure=False):
        _players = _iterableify(players)

        if len(_players) == 0:
            raise ConstraintException('Empty lock group')

        for p in _players:
            if p in self:
                raise ConstraintConflictException(
                    '{} exists in another constraint'.format(p)
                )

        if for_exposure:
            self._locked_for_exposure.update(_players)
        else:
            self._locked.update(_players)

    def clear_exposure_constraints(self):
        self._locked_for_exposure.clear()
        self._banned_for_exposure.clear()


class ConstraintConflictException(Exception):
    pass


class ConstraintIterator(object):
    def __init__(self, constraints):
        self._constraints = constraints
        self.ndx = 0

    def __next__(self):
        if self.ndx >= len(self._constraints):
            raise StopIteration

        r = self._constraints[self.ndx]
        self.ndx += 1
        return r


class AbstractConstraint(ABC):
    @abstractmethod
    def __init__(self):
        super().__init__()

    @abstractmethod
    def __repr__(self):
        pass

    @abstractmethod
    def __str__(self):
        pass

    @abstractmethod
    def __eq__(self, constraint):
        pass

    @abstractmethod
    def __hash__(self):
        pass

    @abstractmethod
    def __contains__(self, player):
        pass

    @abstractmethod
    def apply(self):
        pass


class ConstraintException(Exception):
    pass


class PlayerConstraint(AbstractConstraint):
    def __init__(self, players):
        if not len(players):
            raise ConstraintException('No players in group')

        if len(players) != len(set(players)):
            raise ConstraintException('Duplicate players in group')

        self.players = players

        super().__init__()

    def __eq__(self, rule):
        return set(self.players) == set(rule.players)

    def __hash__(self):
        return hash(''.join(sorted(self.players)))

    def __contains__(self, player):
        return player in self.players


class PlayerGroupConstraint(PlayerConstraint):
    def __init__(self, players, bound):
        super().__init__(players)
        self.exact = None
        self.lo = None
        self.hi = None

        if isinstance(bound, (list, tuple)) and len(bound) == 2:
            self.lo = bound[0]
            self.hi = bound[1]
            self._hi_lo_bounds_sanity_check()
        elif isinstance(bound, int):
            self.exact = bound
            self._exact_bounds_sanity_check()
        else:
            raise ConstraintException('Bound must be length 2 or int')

    def __repr__(self):
        return '<PlayerGroupConstraint: {} of {}>'.format(self._bounds_str,
                                                          self.players)

    def __str__(self):
        ls = ['Using {} of:'.format(self._bounds_str)] + \
             ['\t'+p for p in self.players]
        return '\n'.join(ls)

    def __eq__(self, constraint):
        return super().__eq__(constraint) and self.exact == constraint.exact \
               and self.lo == constraint.lo and self.hi == constraint.hi

    def __hash__(self):
        return hash((super().__hash__(), self.exact, self.lo, self.hi))

    @property
    def _bounds_str(self):
        if self.exact:
            return '{0.exact}'.format(self)

        return '{0.lo} to {0.hi}'.format(self)

    def _exact_bounds_sanity_check(self):
        if self.exact <= 0:
            raise ConstraintException(
                'Exact bound may not less than or equal to zero'
            )
        if self.exact >= len(self.players):
            raise ConstraintException(
                'Exact bound may not be greater than or equal to number '
                'of players in group'
            )

    def _hi_lo_bounds_sanity_check(self):
        if self.lo < 1:
            raise ConstraintException(
                'Lower bound for {!r} cannot be less than 1'.format(self)
            )
        if self.hi == self.lo:
            raise ConstraintException(
                'Lower bound for {!r} cannot equal upper bound'.format(self)
            )
        if self.hi < self.lo:
            raise ConstraintException(
                'Upper bound for {!r} cannot be less than lower bound.'
                .format(self)
            )
        if self.hi > len(self.players) or self.lo > len(self.players):
            raise ConstraintException(
                'Bound for {!r} cannot be greater than number of players '
                'group'.format(self)
            )

    def apply(self):
        pass
