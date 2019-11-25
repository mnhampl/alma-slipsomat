class LetterInfo(object):
    """Interface to "Customize letters" in Alma."""

    def __init__(self, name, index, channel):
        self.name = name
        self.index = index
        self.channel = channel

        self.unique_name = name + '-' + channel if channel else name

#         if channel:
#             self.unique_name = name + '-' + channel 
#         else:
#             self.unique_name = name 
            
    def get_filename(self):
        filename = './' + self.unique_name.replace(' ', '_')

        # file ending
        if not(filename.endswith('.xsl')): 
            filename += '.xsl'
        
        return filename
    