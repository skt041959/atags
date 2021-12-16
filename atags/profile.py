import cProfile, pstats, io, os


def profileit(func):
    def wrapper(*args, **kwargs):
        if profileit.enable_profile:
            datafn = f"{func.__name__}.profile{os.getpid()}"
            prof = cProfile.Profile()
            retval = prof.runcall(func, *args, **kwargs)
            s = io.StringIO()
            sortby = 'cumulative'
            ps = pstats.Stats(prof, stream=s).sort_stats(sortby)
            ps.print_stats()
            with open(datafn, 'w') as perf_file:
                perf_file.write(s.getvalue())
            return retval
        else:
            return func(*args, **kwargs)

    return wrapper


profileit.enable_profile = False
